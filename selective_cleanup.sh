#!/bin/bash
# Выборочная очистка документации - оставляем только значимые файлы

REPO_DIR="/opt/media-lab"
BACKUP_DIR="/opt/media-lab/docs_backup_$(date +%Y%m%d_%H%M%S)"

echo "=== Выборочная очистка документации ==="
echo ""

cd "$REPO_DIR" || exit 1

# Файлы, которые ОСТАВЛЯЕМ (значимые)
KEEP_FILES=(
    # Основные
    "README.md"
    "TZ_Cursor_TG_Media_Service.md"
    
    # Git документация (основной файл, остальные объединим)
    "GIT_WORKFLOW.md"
    
    # Deploy документация (самые важные)
    "deploy/README.md"
    "deploy/INSTALL.md"
    "deploy/DEPLOY_STEPS.md"
    
    # Assets
    "assets/fonts/README.md"
)

echo "✅ Файлы, которые будут СОХРАНЕНЫ:"
for file in "${KEEP_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    fi
done
echo ""

# Файлы для удаления
REMOVE_FILES=(
    # Git документация (дубли, объединим с GIT_WORKFLOW.md)
    "AUTO_COMMIT_GUIDE.md"
    "FILTERING_OPTIONS.md"
    "RECOMMENDATION_FILTERING.md"
    
    # Устаревший анализ и планы
    "DEPLOYMENT_ANALYSIS.md"
    "OPTIMIZATION_CHANGES.md"
    "QUICK_START_IMAGES_ONLY.md"
    "REFACTORING_COMPLETE.md"
    "REFACTORING_SUMMARY.md"
    "RETOUCHER_MODELS_DOCUMENTATION.md"
    "SCALING_IMPLEMENTATION_GUIDE.md"
    "SCALING_PLAN_100-300_USERS.md"
    "SCALING_PLAN_IMAGES_ONLY.md"
    "TESTING_SETUP_30_USERS.md"
    "UPSCALE_MODELS_ANALYSIS.md"
    
    # Docker документация (устаревшая)
    "docker/DOCKER_CLEANUP_README.md"
    "docker/DOCKER_DESKTOP_COMPRESS.md"
    "docker/EXTEND_C_DRIVE_INSTRUCTIONS.md"
    "docker/SOLUTION_EXTEND_C_DRIVE.md"
    
    # Deploy документация (дубли и устаревшая)
    "deploy/DEPLOYMENT_CHECKLIST.md"
    "deploy/deploy/SETUP_AUTO_SSH.md"
    "deploy/PROJECT_ANALYSIS.md"
    "deploy/optimization-summary.md"
    "deploy/QUICK_SERVER_CHOICE.md"
    "deploy/QUICK_START.md"
    "deploy/SERVER_COMMANDS.md"
    "deploy/SERVER_RECOMMENDATIONS.md"
    "deploy/SERVER_UPLOAD_GUIDE.md"
    "deploy/SSH_CONNECTION_GUIDE.md"
    "deploy/SSH_SETUP.md"
    "deploy/STRUCTURE.md"
)

echo "❌ Файлы, которые будут УДАЛЕНЫ (${#REMOVE_FILES[@]}):"
for file in "${REMOVE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  - $file"
    fi
done
echo ""

# Подсчет
TOTAL_MD=$(git ls-files '*.md' | wc -l)
KEEP_COUNT=${#KEEP_FILES[@]}
REMOVE_COUNT=${#REMOVE_FILES[@]}

echo "📊 Статистика:"
echo "  Всего MD файлов: $TOTAL_MD"
echo "  Сохранить: $KEEP_COUNT"
echo "  Удалить: $REMOVE_COUNT"
echo "  После очистки останется: ~$((TOTAL_MD - REMOVE_COUNT))"
echo ""

# Подтверждение
read -p "Продолжить очистку? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Отмена. Файлы не удалены."
    exit 0
fi

# Создаем резервную копию
mkdir -p "$BACKUP_DIR"
echo ""
echo "📦 Создание резервной копии..."

# Удаляем файлы (с резервной копией)
echo ""
echo "Удаление файлов..."
REMOVED=0
for file in "${REMOVE_FILES[@]}"; do
    if [ -f "$file" ]; then
        # Резервная копия
        mkdir -p "$BACKUP_DIR/$(dirname "$file")"
        cp "$file" "$BACKUP_DIR/$file" 2>/dev/null
        
        # Удаление
        git rm "$file" 2>/dev/null || rm "$file"
        echo "  ✓ Удален: $file"
        REMOVED=$((REMOVED + 1))
    fi
done

echo ""
echo "✅ Очистка завершена!"
echo "  Удалено файлов: $REMOVED"
echo "  Резервная копия: $BACKUP_DIR"
echo ""
echo "📝 Следующий шаг: объединить Git документацию в один файл"

