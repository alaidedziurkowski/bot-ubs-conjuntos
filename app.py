import os
import json
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

app = Flask(__name__)

# Conectar ao Google Sheets
def connect_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(os.environ["GOOGLE_SHEETS_KEY"])
    return {
        "consultas": sheet.worksheet("Consultas"),
        "ruas": sheet.worksheet("Ruas_ACS"),
        "slots": sheet.worksheet("Slots_Exames"),
        "sessions": sheet.worksheet("Sessions")
    }

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%d/%m/%Y")
    except:
        return None

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From", "").replace("whatsapp:", "")

    resp = MessagingResponse()
    msg = resp.message()

    sheets = connect_sheets()
    sessions_ws = sheets["sessions"]

    # Buscar sessão existente
    try:
        records = sessions_ws.get_all_records()
        session = next((r for r in records if str(r["Telefone"]) == from_number), None)
    except:
        session = None

    if not session:
        # Nova sessão
        sessions_ws.append_row([from_number, "menu_inicial", datetime.now().strftime("%d/%m/%Y %H:%M:%S"), ""])
        msg.body("Olá! 👋 Bem-vindo à UBS dos Conjuntos".

Escolha uma opção:
1️⃣ Agendar Eletro
2️⃣ Agendar Preventivo
3️⃣ Agendar Consulta")
        return str(resp)

    etapa = session["ÚltimaEtapa"]
    if etapa == "menu_inicial":
        if "1" in incoming_msg or "eletro" in incoming_msg:
            slots = sheets["slots"].get_all_records()
            livres = [s for s in slots if s["Tipo"].lower() == "eletro" and s["Status"].lower() == "livre"]
            if not livres:
                msg.body("❌ Não há horários disponíveis para Eletro.")
            else:
                texto = "Escolha um horário disponível para Eletro:
"
                for i, s in enumerate(livres[:5], start=1):
                    texto += f"{i}️⃣ {s['Data']} {s['Hora']} - {s['Unidade']}
"
                msg.body(texto)
                sessions_ws.update_cell(session["row"], 2, "aguardando_escolha_eletro")
        elif "2" in incoming_msg or "preventivo" in incoming_msg:
            slots = sheets["slots"].get_all_records()
            livres = [s for s in slots if s["Tipo"].lower() == "preventivo" and s["Status"].lower() == "livre"]
            if not livres:
                msg.body("❌ Não há horários disponíveis para Preventivo.")
            else:
                texto = "Escolha um horário disponível para Preventivo:
"
                for i, s in enumerate(livres[:5], start=1):
                    texto += f"{i}️⃣ {s['Data']} {s['Hora']} - {s['Unidade']}
"
                msg.body(texto)
                sessions_ws.update_cell(session["row"], 2, "aguardando_escolha_preventivo")
        elif "3" in incoming_msg or "consulta" in incoming_msg:
            msg.body("Digite o nome da sua rua para localizar o ACS responsável:")
            sessions_ws.update_cell(session["row"], 2, "aguardando_rua")
        else:
            msg.body("Não entendi. Escolha uma opção:
1️⃣ Agendar Eletro
2️⃣ Agendar Preventivo
3️⃣ Agendar Consulta")
    elif etapa == "aguardando_rua":
        ruas = sheets["ruas"].get_all_records()
        rua = next((r for r in ruas if r["Rua"].strip().lower() in incoming_msg), None)
        if rua:
            msg.body(f"O ACS responsável é {rua['ACS']} 📞 {rua['Telefone']}")
            sessions_ws.update_cell(session["row"], 2, "finalizado")
        else:
            msg.body("Rua não encontrada. Tente novamente.")

    return str(resp)

@app.route("/cron/reminders", methods=["GET"])
def cron_reminders():
    token = request.args.get("token")
    if token != os.environ.get("CRON_TOKEN"):
        return "Unauthorized", 403

    sheets = connect_sheets()
    consultas_ws = sheets["consultas"]
    consultas = consultas_ws.get_all_records()

    for i, c in enumerate(consultas, start=2):  # linha 2 em diante
        data = parse_date(c["Data"])
        if not data:
            continue
        hora = c["Hora"]
        dt_consulta = datetime.strptime(f"{c['Data']} {hora}", "%d/%m/%Y %H:%M")
        if dt_consulta - datetime.now() <= timedelta(hours=48) and c["Status"].lower() == "marcado":
            # Enviar lembrete via Twilio (placeholder)
            print(f"Enviar lembrete para {c['Nome']} {c['Telefone']}")
            consultas_ws.update_cell(i, 9, "lembrete_enviado")  # coluna Status

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
