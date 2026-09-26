#!/usr/bin/env bash
#
# Настраивает защиту ветки main: изменения проходят только через pull request.
#
# Запуск:
#   ./scripts/setup-branch-protection.sh
#
# Токен берётся из переменной GH_TOKEN, а если она пуста — из конфигурации
# gh CLI (~/.config/gh/hosts.yml). Нужны права администратора репозитория
# и scope `repo`.
#
# Откат (снять защиту полностью):
#   curl -X DELETE -H "Authorization: token $GH_TOKEN" \
#     https://api.github.com/repos/producedbysavant/simintech-code/branches/main/protection

set -euo pipefail

REPO="${REPO:-producedbysavant/simintech-code}"
BRANCH="${BRANCH:-main}"

if [[ -z "${GH_TOKEN:-}" ]]; then
    GH_CONFIG="${HOME}/.config/gh/hosts.yml"
    if [[ -f "${GH_CONFIG}" ]]; then
        GH_TOKEN=$(awk '/oauth_token:/{t=$2} END{print t}' "${GH_CONFIG}")
    fi
fi
if [[ -z "${GH_TOKEN:-}" ]]; then
    echo "Не найден токен: задайте GH_TOKEN или авторизуйтесь в gh" >&2
    exit 1
fi

# required_approving_review_count: 1 — чужой PR требует ревью.
# enforce_admins: false        — владелец может пушить и мёржить свой PR без
#                                второго ревьюера; иначе собственную правку
#                                не влить. Обратная сторона: защита тогда
#                                не ограничивает самого администратора.
# required_status_checks: null — оставлено сознательно. В текущей конфигурации
#                                это ничего не меняет: админ (единственный
#                                владелец) обходит и required checks, поэтому
#                                красный CI мержится и с ними. Чтобы включить,
#                                заменить null на
#                                {"strict": true, "contexts": ["check"]}, но
#                                сперва сверить, что контекст совпадает
#                                буквально (имя job — в .github/workflows/ci.yml):
#                                несовпавший контекст блокирует PR навсегда.
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

BODY_FILE=$(mktemp)
trap 'rm -f "${BODY_FILE}"' EXIT

echo "Применяю защиту к ${REPO}@${BRANCH}..."
HTTP_CODE=$(curl -sS -o "${BODY_FILE}" -w "%{http_code}" -X PUT \
    -H "Authorization: token ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO}/branches/${BRANCH}/protection" \
    --data-binary "${PAYLOAD}")

if [[ "${HTTP_CODE}" != "200" ]]; then
    echo "Не удалось применить защиту: HTTP ${HTTP_CODE}" >&2
    cat "${BODY_FILE}" >&2
    exit 1
fi

# Проверяем, что настройки действительно применились, а не просто вернулся 200.
ACTUAL=$(curl -sS -H "Authorization: token ${GH_TOKEN}" \
    "https://api.github.com/repos/${REPO}/branches/${BRANCH}/protection")

if ! printf '%s' "${ACTUAL}" | grep -q '"required_approving_review_count": *1'; then
    echo "Ответ получен, но требуемое число ревью не подтвердилось." >&2
    echo "Проверьте настройки ветки вручную: ${REPO}@${BRANCH}" >&2
    exit 1
fi

echo "Готово: защита применена и проверена."
