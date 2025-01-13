import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta
import aiohttp
import asyncio
import re

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
intents.guild_messages = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

TOKEN = 'ТОКЕН ВСТАВЬ'

user_last_message_time = {}

script_dir = os.path.dirname(os.path.abspath(__file__))

config_file = os.path.join(script_dir, 'config.json')
server_file = os.path.join(script_dir, 'server.json')

def load_config():
    """Загрузка данных и настроек из файла."""
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    return None

config = load_config()
if config:
    data = config['data']
    settings = config['settings']
else:
    data = {'whitelist': []}
    settings = {
        'role_delete_threshold': 1,
        'channel_delete_threshold': 1,
        'ban_threshold': 1,
        'role_create_threshold': 1,
        'channel_create_threshold': 1,
        'admin_role_threshold': 3,
        'spam_threshold': 5,
        'spam_time_window': 10,
        'timeout_duration': 60
    }

def save_config(config):
    with open(config_file, 'w') as f:
        json.dump(config, f)

async def save_server_data(guild):
    server_data = {
        'name': guild.name,
        'icon': str(guild.icon_url) if guild.icon else None,
        'roles': [role.name for role in guild.roles],
        'channels': [],
        'categories': []
    }
    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            server_data['categories'].append(channel.name)
        else:
            server_data['channels'].append(channel.name)
    
    with open(server_file, 'w') as f:
        json.dump(server_data, f)

async def load_server_data(guild):
    if os.path.exists(server_file):
        with open(server_file, 'r') as f:
            server_data = json.load(f)
            await guild.edit(name=server_data['name'])
            if server_data['icon']:
                async with aiohttp.ClientSession() as session:
                    async with session.get(server_data['icon']) as resp:
                        if resp.status == 200:
                            icon_data = await resp.read()
                            await guild.edit(icon=icon_data)
            for role_name in server_data['roles']:
                await guild.create_role(name=role_name)
            for category_name in server_data['categories']:
                await guild.create_category(name=category_name)
            for channel_name in server_data['channels']:
                await guild.create_text_channel(name=channel_name)

@bot.command()
@commands.has_permissions(administrator=True)
async def backup(ctx):
    await save_server_data(ctx.guild)
    await ctx.send("Данные о сервере успешно сохранены.")

@bot.command()
@commands.has_permissions(administrator=True)
async def downloadbackup(ctx):
    await load_server_data(ctx.guild)
    await ctx.send("Данные о сервере успешно загружены.")

def get_admin_roles(guild):
    admin_roles = []
    for role in guild.roles:
        if role.permissions.administrator:
            admin_roles.append(role)
    
    if len(admin_roles) > settings['admin_role_threshold']:
        print(f"Количество админ ролей ({len(admin_roles)}) превышает порог ({settings['admin_role_threshold']}).")
        return admin_roles[:settings['admin_role_threshold']]
    return admin_roles

@bot.event
async def on_member_update(before, after):
    admin_roles = get_admin_roles(after.guild)
    for role in admin_roles:
        if role in after.roles and role not in before.roles:
            await after.guild.me.edit(permissions=discord.Permissions.none())
            print(f'Пользователю {after.name} выдана админ роль: {role.name}. Права убраны.')

@bot.command()
@commands.has_permissions(administrator=True)
async def change(ctx):
    await ctx.send(
        "Выберите, что изменить:\n"
        "1. role_delete_threshold (Удаление ролей)\n"
        "2. channel_delete_threshold (Удаление каналов)\n"
        "3. ban_threshold (Баны)\n"
        "4. role_create_threshold (Создание ролей)\n"
        "5. channel_create_threshold (Создание каналов)\n"
        "6. timeout_duration (Время мьюта за спам)\n"
        "7. mention_threshold (Порог массовых упоминаний everyone/here)\n"
        "Введите номер параметра, который хотите изменить:"
    )

    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=30)
        parameter_choice = int(msg.content)

        parameters = {
            1: 'role_delete_threshold',
            2: 'channel_delete_threshold',
            3: 'ban_threshold',
            4: 'role_create_threshold',
            5: 'channel_create_threshold',
            6: 'timeout_duration',
            7: 'mention_threshold'
        }

        if parameter_choice in parameters:
            parameter_name = parameters[parameter_choice]
            await ctx.send(f"Введите новое значение для {parameter_name}:")

            msg = await bot.wait_for('message', check=check, timeout=30)
            new_value = int(msg.content)

            if new_value <= 0:
                await ctx.send("Значение должно быть положительным числом. Попробуйте снова.")
                return

            settings[parameter_name] = new_value
            save_config({'data': data, 'settings': settings})

            await ctx.send(f'Настройка {parameter_name} обновлена на {new_value}.')
        else:
            await ctx.send("Неверный выбор. Пожалуйста, попробуйте снова.")

    except ValueError:
        await ctx.send("Пожалуйста, введите корректное число.")
    except asyncio.TimeoutError:
        await ctx.send("Время ожидания истекло. Пожалуйста, попробуйте снова.")

@bot.event
async def on_guild_role_delete(role):
    try:
        if role.guild.me.guild_permissions.ban_members:
            if len(role.guild.roles) < settings['role_delete_threshold']:
                for member in role.guild.members:
                    await member.ban(reason=f"Удаление роли {role.name}, превышен лимит ролей.")
                    print(f"Забанен пользователь {member.name} за удаление роли {role.name}.")
        else:
            print("У бота нет прав на бан участников.")
    except discord.Forbidden as e:
        print(f"Ошибка в on_guild_role_delete: {e}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")

@bot.event
async def on_channel_delete(channel):
    try:
        if channel.guild.me.guild_permissions.ban_members:
            if len(channel.guild.channels) < settings['channel_delete_threshold']:
                for member in channel.guild.members:
                    await member.ban(reason=f"Удаление канала {channel.name}, превышен лимит каналов.")
                    print(f"Забанен пользователь {member.name} за удаление канала {channel.name}.")
        else:
            print("У бота нет прав на бан участников.")
    except discord.Forbidden as e:
        print(f"Ошибка в on_channel_delete: {e}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")

@bot.event
async def on_member_ban(guild, user):
    try:
        bans = await guild.bans()
        if len(bans) >= settings['ban_threshold']:
            for member in guild.members:
                await member.ban(reason=f"Превышен лимит банов.")
                print(f"Забанен пользователь {member.name} за массовые баны.")
    except discord.Forbidden as e:
        print(f"Ошибка в on_member_ban: {e}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")

@bot.event
async def on_message(message):
    try:
        if message.author == bot.user:
            return

        if re.search(r'http[s]?://', message.content):
            await message.channel.send(f"{message.author.mention}, вы не можете отправлять ссылки!")
            await message.author.edit(timeout=discord.utils.utcnow() + timedelta(seconds=settings['timeout_duration']))
            return

        if message.mention_everyone:
            guild = message.guild
            mention_count = settings.get('mention_count', {})
            user_id = message.author.id

            mention_count[user_id] = mention_count.get(user_id, 0) + 1
            settings['mention_count'] = mention_count

            if mention_count[user_id] >= settings['mention_threshold']:

                await guild.ban(message.author, reason="Масс пинг @everyone/@here")
                print(f"Пользователь {message.author} забанен за масс пинг.")

                del mention_count[user_id]
                return

        current_time = message.created_at.timestamp()
        user_id = message.author.id

        if user_id in user_last_message_time:
            user_last_message_time[user_id].append(current_time)

            user_last_message_time[user_id] = [
                t for t in user_last_message_time[user_id]
                if t > current_time - settings['spam_time_window']
            ]


            if len(user_last_message_time[user_id]) > settings['spam_threshold']:

                await message.channel.send(f"{message.author.mention}, вы спамите! Вы получили таймаут на {settings['timeout_duration']} секунд.")
                

                muted_role = discord.utils.get(message.guild.roles, name="Muted")
                if not muted_role:

                    muted_role = await message.guild.create_role(name="Muted", permissions=discord.Permissions(send_messages=False, speak=False))

                    for channel in message.guild.text_channels:
                        await channel.set_permissions(muted_role, send_messages=False)

                await message.author.add_roles(muted_role)


                await asyncio.sleep(settings['timeout_duration'])


                await message.author.remove_roles(muted_role)

                return
        else:
            user_last_message_time[user_id] = [current_time]


        await bot.process_commands(message)

    except Exception as e:
        print(f"Ошибка в on_message: {e}")

@bot.event
async def on_guild_role_create(role):
    try:
        if role.guild.me.guild_permissions.ban_members:
            if len(role.guild.roles) >= settings['role_create_threshold']:
                async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
                    if entry.target.id == role.id:
                        user = entry.user
                        await user.ban(reason=f"Создание роли {role.name}, превышен лимит ролей.")
                        print(f"Забанен пользователь {user.name} за создание роли {role.name}.")
                        return
                print("Создатель роли не найден в аудиторном логе.")
        else:
            print("У бота нет прав на просмотр аудиторного лога или бан участников.")
    except discord.Forbidden as e:
        print(f"Ошибка в on_guild_role_create: {e}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")

@bot.event
async def on_channel_create(channel):
    try:
        if channel.guild.me.guild_permissions.ban_members:
            if len(channel.guild.channels) >= settings['channel_create_threshold']:
                async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
                    if entry.target.id == channel.id:
                        user = entry.user
                        await user.ban(reason=f"Создание канала {channel.name}, превышен лимит каналов.")
                        print(f"Забанен пользователь {user.name} за создание канала {channel.name}.")
                        return
                print("Создатель канала не найден в аудиторном логе.")
        else:
            print("У бота нет прав на просмотр аудиторного лога или бан участников.")
    except discord.Forbidden as e:
        print(f"Ошибка в on_channel_create: {e}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def whitelist(ctx, member: discord.Member):
    """Добавляет пользователя в whitelist (белый список)."""
    if member.id not in config['data']['whitelist']:
        config['data']['whitelist'].append(member.id)
        save_config(config)
        await ctx.send(f"{member.mention} был добавлен в whitelist.")
    else:
        await ctx.send(f"{member.mention} уже в whitelist.")

@bot.command()
@commands.has_permissions(administrator=True)
async def blacklist(ctx, member: discord.Member):
    """Удаляет пользователя из whitelist (белого списка)."""
    if member.id in config['data']['whitelist']:
        config['data']['whitelist'].remove(member.id)
        save_config(config)
        await ctx.send(f"{member.mention} был удален из whitelist.")
    else:
        await ctx.send(f"{member.mention} не найден в whitelist.")

@bot.command()
@commands.has_permissions(administrator=True)
async def show_whitelist(ctx):
    if not data['whitelist']:
        await ctx.send('Белый список пуст.')
        return

    members = [f'<@{id}>' for id in data['whitelist']]
    await ctx.send('Белый список:\n' + '\n'.join(members))

@bot.command(name='хелп')
@commands.has_permissions(administrator=True)
async def хелп(ctx):
    help_text = (
        "**Доступные команды:**\n"
        "!change - Изменить пороги для антикраша\n"
        "!whitelist [member] [role] - Добавить пользователя или роль в белый список\n"
        "!blacklist [member] [role] - Удалить пользователя или роль из белого списка\n"
        "!show_whitelist - Показать белый список\n"
        "!downloadbackup - Разгружает сервер\n"
        "!backup - Сохраняет сервер\n"
        "!хелп - Показать этот список команд"
    )
    await ctx.send(help_text)

@bot.event
async def on_ready():
    try:
        print(f'Бот {bot.user} запущен!')
        await bot.change_presence(activity=discord.Game(name="Dev 2everyone"))
    except Exception as e:
        print(f"Ошибка в on_ready: {e}")

bot.run(TOKEN)