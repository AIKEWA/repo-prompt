# Repo-Prompt shell aliases (Step 2.11)
# Generated for *bash*.  Source this file from ~/.bashrc:
#   source <path>/repo_prompt_aliases.sh
#
# The aliases provide concise access to common Repo-Prompt utilities.
alias rp="python -m src.prompt \$@"
alias rp-context="python -m src.context_builder.search \$@"
alias rp-diff="python -m src.patch_apply \$@"
alias rp-metrics="python -m src.evaluation_criteria summary \$@"

