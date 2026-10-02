from __future__ import annotations

import asyncio
import os
import threading
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

from dotenv import dotenv_values
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    FloodWaitError,
)

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
ENV = dotenv_values(ROOT / '.env')
API_ID = int(ENV.get('TELEGRAM_API_ID') or 0)
API_HASH = str(ENV.get('TELEGRAM_API_HASH') or '')
PHONE = str(ENV.get('TELEGRAM_PHONE') or '')
SESSION = ROOT / str(ENV.get('TELEGRAM_SESSION_PATH') or 'data/telegram/reader')
SESSION.parent.mkdir(parents=True, exist_ok=True)
MARKER = SESSION.with_suffix('.authorized')
state = {'hash': None, 'need_password': False}

BG = '#0b0f18'
CARD = '#121927'
TEXT = '#eef2ff'
MUTED = '#8fa0be'
ACCENT = '#ff5a1f'
BLUE = '#315e9e'
GREEN = '#235c46'
INPUT_BG = '#0d1421'

root = tk.Tk()
root.title('Conectar Telegram · Shopee Deal Machine')
root.geometry('650x620')
root.minsize(650, 620)
root.configure(bg=BG)
root.resizable(False, False)

frame = tk.Frame(root, bg=CARD, padx=30, pady=24)
frame.place(relx=.5, rely=.5, anchor='center', width=590, height=560)
frame.columnconfigure(0, weight=1)

row = 0

def add_label(text, *, big=False, color=None, pady=(0, 0)):
    global row
    font = ('Segoe UI', 18, 'bold') if big else ('Segoe UI', 9)
    lbl = tk.Label(frame, text=text, font=font, fg=color or (TEXT if big else MUTED), bg=CARD, anchor='w')
    lbl.grid(row=row, column=0, sticky='ew', pady=pady)
    row += 1
    return lbl


def add_entry(show=None):
    global row
    e = tk.Entry(frame, font=('Segoe UI', 11), bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief='flat', show=show)
    e.grid(row=row, column=0, sticky='ew', ipady=9, pady=(0, 3))
    row += 1
    return e

add_label('📡 Conectar conta leitora', big=True)
add_label('Essa conta apenas observa os canais/grupos que você já acessa.', pady=(3, 12))
add_label('O código normalmente chega DENTRO DO APP TELEGRAM, no chat oficial “Telegram”.\nEle pode não chegar por SMS.', color='#ffd37a', pady=(0, 12))

add_label('1. TELEFONE')
phone = add_entry()
phone.insert(0, PHONE)

status = tk.StringVar(value='Pronto para conectar. Clique em “1) Enviar código”.')


def run_async(coro, done):
    def work():
        try:
            res = asyncio.run(coro)
            root.after(0, lambda: done(res, None))
        except Exception as exc:
            root.after(0, lambda: done(None, exc))
    threading.Thread(target=work, daemon=True).start()


def configured():
    if not API_ID or not API_HASH:
        messagebox.showerror('Configuração incompleta', 'Preencha API ID e API Hash na Central Windows primeiro.')
        return False
    return True


def friendly_error(err: Exception) -> str:
    if isinstance(err, PhoneNumberInvalidError):
        return 'O Telegram considerou o número inválido. Confira DDI + DDD + número, começando com +55.'
    if isinstance(err, PhoneCodeInvalidError):
        return 'O código informado é inválido. Confira o código recebido no chat oficial “Telegram”.'
    if isinstance(err, PhoneCodeExpiredError):
        return 'O código expirou. Clique em “1) Enviar código” novamente para receber outro.'
    if isinstance(err, FloodWaitError):
        seconds = getattr(err, 'seconds', None)
        if seconds:
            return f'O Telegram pediu para aguardar {seconds} segundos antes de tentar novamente.'
        return 'Muitas tentativas foram feitas. Aguarde um pouco e tente novamente.'
    return str(err)


async def send_code_async(ph):
    client = TelegramClient(str(SESSION), API_ID, API_HASH)
    await client.connect()
    try:
        if await client.is_user_authorized():
            MARKER.write_text('ok', encoding='utf-8')
            return {'authorized': True}
        sent = await client.send_code_request(ph)
        return {
            'authorized': False,
            'hash': sent.phone_code_hash,
            'type': type(getattr(sent, 'type', None)).__name__,
            'next_type': type(getattr(sent, 'next_type', None)).__name__ if getattr(sent, 'next_type', None) is not None else '',
        }
    finally:
        await client.disconnect()


def send_code():
    if not configured():
        return
    ph = phone.get().strip()
    if not ph:
        messagebox.showwarning('Telefone', 'Informe o telefone com DDI, por exemplo +55...')
        return
    send_btn.config(state='disabled')
    status.set('Enviando pedido de código ao Telegram…')

    def done(res, err):
        send_btn.config(state='normal')
        if err:
            status.set('Falha ao solicitar o código.')
            messagebox.showerror('Telegram', friendly_error(err))
            return
        if res.get('authorized'):
            status.set('Conta já está conectada ✅')
            messagebox.showinfo('Telegram', 'Essa conta já está autenticada.')
            return
        state['hash'] = res['hash']
        delivery = res.get('type') or 'Telegram'
        status.set(f'Código solicitado com sucesso ({delivery}). Confira o app Telegram e digite abaixo.')
        code.focus_set()
        messagebox.showinfo(
            'Código solicitado',
            'Pedido enviado ao Telegram.\n\nAbra o APP TELEGRAM da sua conta e procure o chat oficial “Telegram”. '
            'O código geralmente aparece ali, e não necessariamente por SMS.\n\nDepois digite o código nesta janela e clique em “2) Confirmar código”.'
        )

    run_async(send_code_async(ph), done)


send_btn = tk.Button(
    frame,
    text='1) ENVIAR CÓDIGO',
    command=send_code,
    bg=ACCENT,
    fg='white',
    activebackground=ACCENT,
    activeforeground='white',
    relief='flat',
    font=('Segoe UI', 10, 'bold'),
    pady=10,
)
send_btn.grid(row=row, column=0, sticky='ew', pady=(8, 14))
row += 1

add_label('2. CÓDIGO RECEBIDO NO TELEGRAM')
code = add_entry()


async def sign_code_async(ph, cd, phash):
    client = TelegramClient(str(SESSION), API_ID, API_HASH)
    await client.connect()
    try:
        if await client.is_user_authorized():
            MARKER.write_text('ok', encoding='utf-8')
            return {'ok': True}
        try:
            await client.sign_in(phone=ph, code=cd, phone_code_hash=phash)
            MARKER.write_text('ok', encoding='utf-8')
            return {'ok': True}
        except SessionPasswordNeededError:
            return {'need_password': True}
    finally:
        await client.disconnect()


def confirm_code():
    if not configured():
        return
    if not state.get('hash'):
        messagebox.showwarning('Código', 'Clique primeiro em “1) Enviar código”.')
        return
    ph = phone.get().strip()
    cd = code.get().strip().replace(' ', '')
    if not cd:
        messagebox.showwarning('Código', 'Digite o código recebido no Telegram.')
        return
    confirm_btn.config(state='disabled')
    status.set('Confirmando código…')

    def done(res, err):
        confirm_btn.config(state='normal')
        if err:
            status.set('Código não confirmado.')
            messagebox.showerror('Telegram', friendly_error(err))
            return
        if res.get('need_password'):
            state['need_password'] = True
            status.set('Sua conta usa 2FA. Digite a senha abaixo e clique em “3) Confirmar 2FA”.')
            password.focus_set()
            return
        status.set('Telegram conectado com sucesso ✅')
        messagebox.showinfo('Pronto', 'Conta leitora conectada. Você pode fechar esta janela.')

    run_async(sign_code_async(ph, cd, state['hash']), done)


confirm_btn = tk.Button(
    frame,
    text='2) CONFIRMAR CÓDIGO',
    command=confirm_code,
    bg=BLUE,
    fg='white',
    activebackground=BLUE,
    activeforeground='white',
    relief='flat',
    font=('Segoe UI', 10, 'bold'),
    pady=9,
)
confirm_btn.grid(row=row, column=0, sticky='ew', pady=(7, 12))
row += 1

add_label('3. SENHA 2FA (SÓ SE FOR PEDIDA)')
password = add_entry('•')


async def sign_password_async(pw):
    client = TelegramClient(str(SESSION), API_ID, API_HASH)
    await client.connect()
    try:
        if await client.is_user_authorized():
            MARKER.write_text('ok', encoding='utf-8')
            return True
        await client.sign_in(password=pw)
        MARKER.write_text('ok', encoding='utf-8')
        return True
    finally:
        await client.disconnect()


def confirm_password():
    if not state.get('need_password'):
        messagebox.showwarning('2FA', 'Confirme primeiro o código recebido.')
        return
    pw = password.get()
    if not pw:
        messagebox.showwarning('2FA', 'Digite sua senha de verificação em duas etapas.')
        return
    pass_btn.config(state='disabled')
    status.set('Confirmando 2FA…')

    def done(res, err):
        pass_btn.config(state='normal')
        if err:
            status.set('Senha 2FA não confirmada.')
            messagebox.showerror('Telegram', friendly_error(err))
            return
        status.set('Telegram conectado com sucesso ✅')
        messagebox.showinfo('Pronto', 'Conta leitora conectada. Você pode fechar esta janela.')

    run_async(sign_password_async(pw), done)


pass_btn = tk.Button(
    frame,
    text='3) CONFIRMAR 2FA',
    command=confirm_password,
    bg=GREEN,
    fg='white',
    activebackground=GREEN,
    activeforeground='white',
    relief='flat',
    font=('Segoe UI', 10, 'bold'),
    pady=9,
)
pass_btn.grid(row=row, column=0, sticky='ew', pady=(7, 10))
row += 1

status_lbl = tk.Label(
    frame,
    textvariable=status,
    font=('Segoe UI', 9),
    fg='#9fd3b3',
    bg=CARD,
    wraplength=520,
    justify='left',
    anchor='w',
)
status_lbl.grid(row=row, column=0, sticky='ew', pady=(3, 0))

root.bind('<Return>', lambda event: confirm_code() if state.get('hash') and code.get().strip() else send_code())
root.mainloop()
