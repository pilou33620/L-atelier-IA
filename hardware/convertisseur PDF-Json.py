# ==============================================================================
# Version: 1.0.1
# Date: 2026-07-16
# Description: Outil complet de conversion PDF vers JSON hybride (Markdown + Images)
# avec interface graphique Tkinter. Extraction du texte et des images dans un dossier dédié.
# Fonctions modifiées/ajoutées :
# - convert_pdf_to_markdown (Modifiée)
# ==============================================================================

import os
import json
import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog, messagebox


def extract_images_from_page(page: fitz.Page, image_folder_path: str, page_num: int,
                             doc: fitz.Document, link_prefix: str = "") -> str:
    """
    Extrait les images d'une page PDF spécifique, les sauvegarde dans le dossier
    indiqué et retourne une chaîne de caractères contenant les balises Markdown.

    V4.4.0 : 'link_prefix' permet d'écrire dans le JSON des chemins relatifs à
    la RACINE DU PROJET (ex: 'data_sheets/lm555_images/...') et non au dossier
    du composant — sans quoi l'outil read_image des agents (qui résout les
    chemins depuis la racine) ne trouvait jamais les images.
    """
    image_list = page.get_images(full=True)
    md_image_links = ""
    
    if image_list:
        for image_index, img in enumerate(image_list, start=1):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # Création du nom de l'image
            image_name = f"page_{page_num}_img_{image_index}.{image_ext}"
            image_path = os.path.join(image_folder_path, image_name)
            
            # Sauvegarde de l'image sur le disque
            with open(image_path, "wb") as image_file:
                image_file.write(image_bytes)
            
            # Ajout du lien Markdown (chemins POSIX, préfixe racine projet)
            folder_name = os.path.basename(image_folder_path)
            md_image_links += (f"\n![Image_page_{page_num}_{image_index}]"
                               f"({link_prefix}{folder_name}/{image_name})\n")
            
    return md_image_links


def convert_pdf_to_markdown(pdf_path: str, output_dir: str, link_prefix: str = "") -> None:
    """
    Fonction principale de conversion. Crée le dossier d'images, extrait le texte
    et les images du PDF, puis sauvegarde le tout dans un fichier JSON hybride.
    'link_prefix' est préfixé aux chemins d'images stockés dans le JSON (voir
    extract_images_from_page).
    """
    # Préparation des noms de fichiers et de dossiers
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    json_filename = f"{base_name}.json"
    json_filepath = os.path.join(output_dir, json_filename)
    
    image_folder_name = f"{base_name}_images"
    image_folder_path = os.path.join(output_dir, image_folder_name)
    
    # Création du dossier d'images s'il n'existe pas
    os.makedirs(image_folder_path, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    
    # Liste globale pour stocker les dictionnaires de chaque page
    document_data = []
    
    # Parcours de toutes les pages du PDF
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        
        # Extraction du texte brut
        text = page.get_text()
        
        # Extraction des images sur le disque et récupération des liens Markdown générés
        image_markdown = extract_images_from_page(page, image_folder_path, page_num + 1,
                                                  doc, link_prefix=link_prefix)
        
        # Extraction des chemins d'images à partir de la chaîne Markdown retournée
        image_paths = []
        for line in image_markdown.split('\n'):
            if line.startswith('![') and '](' in line:
                path = line.split('](')[1].split(')')[0]
                image_paths.append(path)
        
        # Création du bloc structuré pour la page courante
        page_data = {
            "page": page_num + 1,
            "texte_markdown": text.strip(),
            "images": image_paths
        }
        
        document_data.append(page_data)
        
    doc.close()
    
    # Écriture du fichier JSON final
    with open(json_filepath, "w", encoding="utf-8") as json_file:
        json.dump(document_data, json_file, indent=4, ensure_ascii=False)


def process_multiple_pdfs(pdf_paths: list, base_output_dir: str) -> None:
    """
    Convertit chaque PDF dans le dossier 'data_sheets/' du projet.

    BUGFIX CRITIQUE (V4.4.0) : l'ancienne version écrivait dans
    'datasheet/<composant>/<composant>.json' alors que l'Agent Composant
    (agents_hardware.json) est STRICTEMENT borné par son prompt au dossier
    'data_sheets/' avec des fichiers À PLAT (ex: 'data_sheets/lm555.json').
    Double décalage (nom du dossier + imbrication) : l'agent ne trouvait
    JAMAIS les datasheets importées via le bouton dédié. On écrit désormais :
      - data_sheets/<composant>.json
      - data_sheets/<composant>_images/...
    et les chemins d'images du JSON sont relatifs à la racine du projet
    (data_sheets/<composant>_images/...), utilisables tels quels par
    read_image.
    """
    datasheet_dir = os.path.join(base_output_dir, "data_sheets")
    os.makedirs(datasheet_dir, exist_ok=True)
    
    for pdf_path in pdf_paths:
        convert_pdf_to_markdown(pdf_path, datasheet_dir, link_prefix="data_sheets/")


def select_pdf(label_var: tk.StringVar, pdf_paths_list: list) -> None:
    """
    Ouvre une fenêtre pour sélectionner un ou plusieurs fichiers PDF sources.
    """
    file_paths = filedialog.askopenfilenames(
        title="Sélectionner des fichiers PDF",
        filetypes=[("Fichiers PDF", "*.pdf")]
    )
    if file_paths:
        pdf_paths_list.clear()
        pdf_paths_list.extend(file_paths)
        if len(file_paths) == 1:
            label_var.set(file_paths[0])
        else:
            label_var.set(f"{len(file_paths)} fichiers sélectionnés")


def select_output_dir(label_var: tk.StringVar) -> None:
    """
    Ouvre une fenêtre pour sélectionner le dossier de destination.
    """
    dir_path = filedialog.askdirectory(
        title="Sélectionner le dossier de destination"
    )
    if dir_path:
        label_var.set(dir_path)


def start_conversion(pdf_paths: list, output_dir_var: tk.StringVar) -> None:
    """
    Vérifie les données de l'interface et lance la conversion en lot.
    """
    output_dir = output_dir_var.get()
    
    if not pdf_paths:
        messagebox.showwarning("Attention", "Veuillez sélectionner au moins un fichier PDF.")
        return
        
    if not output_dir or output_dir == "Aucun dossier sélectionné":
        messagebox.showwarning("Attention", "Veuillez sélectionner un dossier de destination.")
        return
        
    try:
        process_multiple_pdfs(pdf_paths, output_dir)
        messagebox.showinfo("Succès", "La conversion est terminée avec succès !")
    except Exception as e:
        messagebox.showerror("Erreur", f"Une erreur est survenue lors de la conversion :\n{str(e)}")


def main() -> None:
    """
    Initialisation et configuration de la fenêtre principale Tkinter.
    """
    root = tk.Tk()
    root.title("Convertisseur PDF vers Markdown")
    root.geometry("600x250")
    root.resizable(False, False)
    
    # Variables pour stocker les chemins
    pdf_paths_list = []
    pdf_path_var = tk.StringVar(value="Aucun fichier sélectionné")
    output_dir_var = tk.StringVar(value="Aucun dossier sélectionné")
    
    # Section Sélection du PDF
    tk.Label(root, text="Fichiers PDF sources :", font=("Arial", 10, "bold")).pack(pady=(15, 0))
    lbl_pdf = tk.Label(root, textvariable=pdf_path_var, fg="blue")
    lbl_pdf.pack()
    btn_pdf = tk.Button(root, text="Parcourir les PDF", command=lambda: select_pdf(pdf_path_var, pdf_paths_list))
    btn_pdf.pack(pady=5)
    
    # Section Sélection du dossier de destination
    tk.Label(root, text="Dossier de destination (base pour le dossier datasheet) :", font=("Arial", 10, "bold")).pack(pady=(15, 0))
    lbl_dir = tk.Label(root, textvariable=output_dir_var, fg="blue")
    lbl_dir.pack()
    btn_dir = tk.Button(root, text="Parcourir la destination", command=lambda: select_output_dir(output_dir_var))
    btn_dir.pack(pady=5)
    
    # Bouton de conversion
    btn_convert = tk.Button(root, text="Lancer la conversion", bg="green", fg="white", font=("Arial", 10, "bold"),
                            command=lambda: start_conversion(pdf_paths_list, output_dir_var))
    btn_convert.pack(pady=20)
    
    root.mainloop()


if __name__ == "__main__":
    main()