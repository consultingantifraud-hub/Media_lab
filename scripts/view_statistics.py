#!/usr/bin/env python3
"""Script to view user statistics from database."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.db.models import User, UserStatistics, Operation, Balance
from sqlalchemy import func, desc
import json
from datetime import datetime


def format_date(dt):
    """Format datetime for display."""
    if not dt:
        return "N/A"
    if isinstance(dt, str):
        return dt
    return dt.strftime("%d.%m.%Y %H:%M")


def view_all_statistics():
    """View statistics for all users."""
    db = SessionLocal()
    try:
        # Get all users with statistics
        users = db.query(User).order_by(desc(User.created_at)).all()
        
        print("\n" + "="*80)
        print("📊 СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ")
        print("="*80)
        print(f"Всего пользователей: {len(users)}\n")
        
        for user in users:
            stats = db.query(UserStatistics).filter(UserStatistics.user_id == user.id).first()
            balance = db.query(Balance).filter(Balance.user_id == user.id).first()
            
            print(f"👤 Пользователь ID: {user.id}")
            print(f"   Telegram ID: {user.telegram_id}")
            print(f"   Username: @{user.username}" if user.username else "   Username: не указан")
            print(f"   Имя: {user.first_name or 'не указано'} {user.last_name or ''}")
            print(f"   Язык: {user.language_code or 'не указан'}")
            print(f"   Premium: {'Да' if user.is_premium else 'Нет'}")
            print(f"   Регистрация: {format_date(user.created_at)}")
            print(f"   Последняя активность: {format_date(user.last_activity_at)}")
            print(f"   Баланс: {balance.balance if balance else 0} ₽")
            
            if stats:
                print(f"   📈 Статистика:")
                print(f"      Всего операций: {stats.total_operations}")
                print(f"      Всего потрачено: {stats.total_spent} ₽")
                print(f"      Первая операция: {format_date(stats.first_operation_at)}")
                print(f"      Последняя операция: {format_date(stats.last_operation_at)}")
                
                if stats.operations_by_type:
                    try:
                        ops_by_type = json.loads(stats.operations_by_type)
                        print(f"      Операции по типам:")
                        for op_type, count in sorted(ops_by_type.items(), key=lambda x: x[1], reverse=True):
                            print(f"         • {op_type}: {count}")
                    except:
                        pass
                
                if stats.models_used:
                    try:
                        models = json.loads(stats.models_used)
                        print(f"      Использованные модели:")
                        for model, count in sorted(models.items(), key=lambda x: x[1], reverse=True):
                            print(f"         • {model}: {count}")
                    except:
                        pass
            else:
                print(f"   📈 Статистика: нет данных")
            
            print()
        
        # Общая статистика
        print("="*80)
        print("📊 ОБЩАЯ СТАТИСТИКА")
        print("="*80)
        
        total_users = db.query(func.count(User.id)).scalar()
        total_operations = db.query(func.count(Operation.id)).filter(
            Operation.status.in_(["charged", "free"])
        ).scalar()
        total_spent = db.query(func.sum(Operation.price)).filter(
            Operation.status == "charged"
        ).scalar() or 0
        
        print(f"Всего пользователей: {total_users}")
        print(f"Всего операций: {total_operations}")
        print(f"Всего заработано: {total_spent} ₽")
        
        # Статистика по типам операций
        ops_by_type = db.query(
            Operation.type,
            func.count(Operation.id).label('count')
        ).filter(
            Operation.status.in_(["charged", "free"])
        ).group_by(Operation.type).all()
        
        if ops_by_type:
            print("\nОперации по типам:")
            for op_type, count in sorted(ops_by_type, key=lambda x: x[1], reverse=True):
                print(f"   • {op_type}: {count}")
        
        # Статистика по моделям
        models_used = db.query(
            Operation.model,
            func.count(Operation.id).label('count')
        ).filter(
            Operation.status.in_(["charged", "free"]),
            Operation.model.isnot(None)
        ).group_by(Operation.model).all()
        
        if models_used:
            print("\nИспользованные модели:")
            for model, count in sorted(models_used, key=lambda x: x[1], reverse=True):
                print(f"   • {model}: {count}")
        
        print("="*80 + "\n")
        
    finally:
        db.close()


def view_user_statistics(telegram_id: int):
    """View statistics for a specific user."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            print(f"❌ Пользователь с Telegram ID {telegram_id} не найден")
            return
        
        stats = db.query(UserStatistics).filter(UserStatistics.user_id == user.id).first()
        balance = db.query(Balance).filter(Balance.user_id == user.id).first()
        operations = db.query(Operation).filter(
            Operation.user_id == user.id
        ).order_by(desc(Operation.created_at)).limit(10).all()
        
        print("\n" + "="*80)
        print(f"👤 СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ")
        print("="*80)
        print(f"ID: {user.id}")
        print(f"Telegram ID: {user.telegram_id}")
        print(f"Username: @{user.username}" if user.username else "Username: не указан")
        print(f"Имя: {user.first_name or 'не указано'} {user.last_name or ''}")
        print(f"Язык: {user.language_code or 'не указан'}")
        print(f"Premium: {'Да' if user.is_premium else 'Нет'}")
        print(f"Регистрация: {format_date(user.created_at)}")
        print(f"Последняя активность: {format_date(user.last_activity_at)}")
        print(f"Баланс: {balance.balance if balance else 0} ₽")
        
        if stats:
            print(f"\n📈 Агрегированная статистика:")
            print(f"   Всего операций: {stats.total_operations}")
            print(f"   Всего потрачено: {stats.total_spent} ₽")
            print(f"   Первая операция: {format_date(stats.first_operation_at)}")
            print(f"   Последняя операция: {format_date(stats.last_operation_at)}")
            
            if stats.operations_by_type:
                try:
                    ops_by_type = json.loads(stats.operations_by_type)
                    print(f"\n   Операции по типам:")
                    for op_type, count in sorted(ops_by_type.items(), key=lambda x: x[1], reverse=True):
                        print(f"      • {op_type}: {count}")
                except:
                    pass
            
            if stats.models_used:
                try:
                    models = json.loads(stats.models_used)
                    print(f"\n   Использованные модели:")
                    for model, count in sorted(models.items(), key=lambda x: x[1], reverse=True):
                        print(f"      • {model}: {count}")
                except:
                    pass
        
        if operations:
            print(f"\n📋 Последние 10 операций:")
            for op in operations:
                status_emoji = "✅" if op.status == "charged" else "⏳" if op.status == "pending" else "❌"
                print(f"   {status_emoji} {op.type} | {op.price} ₽ | {format_date(op.created_at)}")
                if op.model:
                    print(f"      Модель: {op.model}")
        
        print("="*80 + "\n")
        
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            telegram_id = int(sys.argv[1])
            view_user_statistics(telegram_id)
        except ValueError:
            print("❌ Ошибка: telegram_id должен быть числом")
            sys.exit(1)
    else:
        view_all_statistics()





