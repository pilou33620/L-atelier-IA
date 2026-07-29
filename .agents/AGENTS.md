# Custom Implementation Plan Rules

- **Strict User Validation**: ALWAYS stop and wait for the user's explicit approval before proceeding to execution for any implementation plan. Do not self-validate or auto-validate plans. Present the plan using the `implementation_plan.md` artifact (with `request_feedback = true` and `user_facing = true`) and STOP execution. Do not execute any steps until the user explicitly responds with approval.
