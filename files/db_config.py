import mysql.connector

def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="sandile",
        password="1234",
        database="unizulu_bot"
    )
    return conn