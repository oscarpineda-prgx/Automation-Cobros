python -m pip install -r requirements.txt
python -m PyInstaller --noconsole --onefile --name AutomationCobros --add-data "templates\Soriana-Logo.png;templates" main.py
