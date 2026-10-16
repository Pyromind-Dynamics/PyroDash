# Shared helpers for the entropy-routing API.
experiment_name_from_model_path() {
  local model_path="$1"
  local parent grandparent
  parent="$(basename "$(dirname "${model_path}")")"
  if [[ "${parent}" == "checkpoints" ]]; then
    grandparent="$(basename "$(dirname "$(dirname "${model_path}")")")"
    printf '%s\n' "${grandparent}"
  else
    printf '%s\n' "${parent}"
  fi
}
