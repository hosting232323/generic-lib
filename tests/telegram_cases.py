"""Formati di produzione dei messaggi Telegram, condivisi tra test e registrazione cassette."""

CASES = [
  (
    'messaggio_semplice',
    '🧪 TEST lib: messaggio semplice',
  ),
  (
    'report_mismatch_troncato',
    '🧪 TEST lib\n*📊 Report Check Mismatch*\n▶️ Photos\n\n'
    '*❌ File presenti solo nel DB (75):*\n```\n'
    + '\n'.join(f'- {i:03}.png' for i in range(50))
    + '\n- … e altri 25 file\n```\n'
    '✔️ Nessun file solo in storage',
  ),
  (
    'blocco_codice_gigante',
    '🧪 TEST lib\n*Report*\n```\n' + '\n'.join(f'- {i}.png' for i in range(1200)) + '\n```',
  ),
  (
    'errore_con_traceback_e_json',
    '🧪 TEST lib\n**Errore:**\n```\nTraceback (most recent call last):\n'
    '  File "/app/src/end_points/rae/__init__.py", line 12\n'
    "    raise ValueError('FIR gia_ presente [id=3]')\n```\n\n"
    '**Request Data:**\n```json\n{"path": "/api/checks", "method": "GET"}\n```',
  ),
  (
    'markdown_sbilanciato',
    '🧪 TEST lib: file_name *incompleto [strano].png con `backtick e (parentesi)',
  ),
]
