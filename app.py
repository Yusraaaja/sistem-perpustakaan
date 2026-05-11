from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('perpustakaan.db')
    conn.row_factory = sqlite3.Row # memanggil data dengan nama kolom
    return conn

@app.route('/')
def index():
    return "<h1>Selamat Datang di Sistem Perpustakaan Digital</h1><p>Gunakan /search untuk mencari buku.</p>"

@app.route('/search')
def search():
    query = request.args.get('query')
    results = []
    if query:
        conn = get_db_connection()
        # mencari buku berdasarkan judul (case insensisive)
        results = conn.execute('SELECT * FROM buku WHERE judul LIKE ?', ('%' + query + '%',)).fetchall()
        conn.close()

    return f"Hasil pencarian untuk '{query}': {[dict(row) for row in results]}"

if __name__ == '__main__':
    app.run(debug=True)