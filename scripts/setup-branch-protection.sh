#!/usr/bin/env bash
#
# Настраивает защиту ветки main: прямой push запрещён, изменения проходят
# только через pull request.
#
# Запуск:
#   scripts/setup-branch-protection.sh
#
# Токен берётся из переменной GH_TOKEN, а если она пуста — из конфигурации
# gh CLI (~/.config/gh/hosts.yml). Нужны права администратора репозитория
# и scope `repo`.
#
# Откат (снять защиту полностью):
#   curl -X DELETE -H "Authorization: token $GH_TOKEN" \
#     https://api.github.com/repos/producedbysavant/simintech-code-library/branches/main/protection

set -euo pipefail

REPO="${REPO:-producedbysavant/simintech-code-library}"
BRANCH="${BRANCH:-main}"

if [[ -z "${GH_TOKEN:-}" ]]; then
    GH_TOKEN=$(awk '/oauth_token:/{t=$2} END{print t}' "$HOME/.config/gh/hosts.yml")
fi
if [[ -z "${GH_TOKEN:-}" ]]; then
    echo "Не найден токен: задайте GH_TOKEN или авторизуйтесь в gh" >&2
    exit 1
fi

# required_approving_review_count: 1 — чужой PR требует ревью.
# enforce_admins: false        — владелец может смержить свой PR без второго
#                                ревьюера; иначе собственную правку не влить.
read -r -d '' PAYLOAD <<'JSON' || true
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON

echo "Применяю защиту к ${REPO}@${BRANCH}..."
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X PUT \
    -H "Authorization: token ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO}/branches/${BRANCH}/protection" \
    --data-binary "${PAYLOAD}"
