from flask import Flask, render_template
from threading import Thread

app = Flask('')

@app.route('/', methods=['get', 'post'])
def home():
    return "Roti Bot Webserver is Online!"
    return render_template('index.html')

def run():
  app.run(host='0.0.0.0', port=8080)

def keep_alive():
   t = Thread(target=run)
   t.start()
