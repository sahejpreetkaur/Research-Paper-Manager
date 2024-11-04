# -*- coding: utf-8 -*-
"""TASK_1.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1izkCmnHo0S-iIhFQtuoeqVQD3xAu3uI-
"""

pip install PyPDF2 numpy sentence-transformers scikit-learn



import os
import sqlite3
import PyPDF2
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
import hashlib

# Load the pre-trained model for generating embeddings
model = SentenceTransformer('all-MiniLM-L6-v2')

def init_db():
    conn = sqlite3.connect('research_papers.db')
    c = conn.cursor()
    # Create tables if they don't exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS research_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            author TEXT,
            publication_date TEXT,
            publication_name TEXT,
            content TEXT,
            last_updated TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS embeddings (
            paper_id INTEGER,
            embedding BLOB,
            FOREIGN KEY (paper_id) REFERENCES research_papers (id)
        )
    ''')
    conn.commit()
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    conn = init_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                  (username, hash_password(password)))
        conn.commit()
        print("User registered successfully.")
    except sqlite3.IntegrityError:
        print("Username already exists. Please choose a different one.")
    finally:
        conn.close()

def login_user(username, password):
    conn = init_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?",
              (username, hash_password(password)))
    user = c.fetchone()
    conn.close()
    return user is not None

def extract_content(reader):
    content = ""
    for page in reader.pages:
        content += page.extract_text() + "\n"
    return content.strip()

def generate_embedding(text):
    return model.encode(text)

def upload_pdf(file_path):
    if os.path.isfile(file_path) and file_path.endswith('.pdf'):
        conn = init_db()
        c = conn.cursor()

        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            title = reader.metadata.title if reader.metadata.title else "Untitled"
            author = reader.metadata.author if reader.metadata.author else "Unknown"
            publication_date = reader.metadata.creation_date if reader.metadata.creation_date else "Unknown"
            publication_name = os.path.basename(file_path)
            content = extract_content(reader)
            embedding = generate_embedding(content)

            # Insert paper details into the database
            c.execute('''
                INSERT INTO research_papers (title, author, publication_date, publication_name, content)
                VALUES (?, ?, ?, ?, ?)
            ''', (title, author, publication_date, publication_name, content))

            # Store embedding in the embeddings table
            c.execute('INSERT INTO embeddings (paper_id, embedding) VALUES (?, ?)', (c.lastrowid, embedding.tobytes()))

        conn.commit()
        conn.close()
        print(f"Uploaded '{title}' successfully.")
    else:
        print("Invalid file path or file is not a PDF.")

def search_papers(keyword, sort_by, filter_by):
    conn = init_db()
    c = conn.cursor()

    # Build the search query
    query = f'''
        SELECT title, author, publication_date, publication_name FROM research_papers
        WHERE title LIKE ? OR author LIKE ?
    '''
    filter_condition = f' AND publication_name LIKE ?' if filter_by else ''
    final_query = query + filter_condition + f' ORDER BY {sort_by}'

    # Execute the query
    params = [f'%{keyword}%', f'%{keyword}%']
    if filter_by:
        params.append(f'%{filter_by}%')

    c.execute(final_query, params)
    results = c.fetchall()
    conn.close()

    if not results:
        raise ValueError("No papers found with the given criteria.")

    return results

def semantic_search(query):
    conn = init_db()
    c = conn.cursor()

    # Generate embedding for the query
    query_embedding = generate_embedding(query)

    # Retrieve all embeddings from the database
    c.execute("SELECT paper_id, embedding FROM embeddings")
    embeddings = c.fetchall()

    # Calculate cosine similarity
    similarities = []
    for paper_id, embedding in embeddings:
        paper_embedding = np.frombuffer(embedding, dtype=np.float32)
        similarity = np.dot(query_embedding, paper_embedding) / (np.linalg.norm(query_embedding) * np.linalg.norm(paper_embedding))
        similarities.append((paper_id, similarity))

    # Sort papers by similarity
    similarities.sort(key=lambda x: x[1], reverse=True)

    # Retrieve top results
    top_results = []
    for paper_id, _ in similarities[:5]:  # Adjust the number of results as needed
        c.execute("SELECT title, author, publication_date, publication_name FROM research_papers WHERE id = ?", (paper_id,))
        top_results.append(c.fetchone())

    conn.close()
    return top_results

def search_tfidf(query):
    conn = init_db()
    c = conn.cursor()

    # Retrieve all contents for TF-IDF
    c.execute("SELECT content FROM research_papers")
    contents = [row[0] for row in c.fetchall()]

    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(contents)

    # Transform the query
    query_vec = vectorizer.transform([query])

    # Calculate similarity scores
    results = (tfidf_matrix * query_vec.T).toarray().flatten()

    # Get top results based on scores
    top_indices = np.argsort(results)[::-1][:5]  # Get indices of top 5 results
    top_results = []

    for index in top_indices:
        c.execute("SELECT title, author, publication_date, publication_name FROM research_papers WHERE id = ?", (index + 1,))
        top_results.append(c.fetchone())

    conn.close()
    return top_results

def batch_update_embeddings():
    conn = init_db()
    c = conn.cursor()

    # Retrieve all papers
    c.execute("SELECT id, content FROM research_papers")
    papers = c.fetchall()

    for paper_id, content in papers:
        new_embedding = generate_embedding(content)

        # Update embedding in the embeddings table
        c.execute("UPDATE embeddings SET embedding = ? WHERE paper_id = ?", (new_embedding.tobytes(), paper_id))
        # Update last_updated timestamp
        c.execute("UPDATE research_papers SET last_updated = CURRENT_TIMESTAMP WHERE id = ?", (paper_id,))

    conn.commit()
    conn.close()
    print("Embeddings updated successfully.")

def batch_index_pdfs(directory):
    for filename in os.listdir(directory):
        if filename.endswith('.pdf'):
            file_path = os.path.join(directory, filename)
            upload_pdf(file_path)

def main():
    while True:
        print("\nOptions:")
        print("1: Register")
        print("2: Login")
        print("3: Upload a new PDF")
        print("4: Search for research papers")
        print("5: Update embeddings")
        print("6: Batch indexing for multiple PDFs in a directory")
        print("7: Exit")
        choice = input("Choose an option (1-7): ")

        if choice == '1':
            username = input("Enter username: ")
            password = input("Enter password: ")
            register_user(username, password)

        elif choice == '2':
            username = input("Enter username: ")
            password = input("Enter password: ")
            if login_user(username, password):
                print("Login successful.")
                while True:
                    print("\nLogged in Options:")
                    print("1: Upload a new PDF")
                    print("2: Search for research papers")
                    print("3: Update embeddings")
                    print("4: Batch indexing for multiple PDFs in a directory")
                    print("5: Logout")
                    logged_in_choice = input("Choose an option (1-5): ")

                    if logged_in_choice == '1':
                        file_path = input("Enter the path of the PDF file to upload: ")
                        upload_pdf(file_path)

                    elif logged_in_choice == '2':
                        keyword = input("Enter a keyword or author name to search: ")
                        sort_by = input("Sort by (title, author, publication_date, publication_name): ")
                        filter_by = input("Filter by publication name (leave blank for no filter): ")
                        try:
                            results = search_papers(keyword, sort_by, filter_by)
                            if results:
                                for row in results:
                                    print(f"Title: {row[0]}, Author: {row[1]}, Publication Date: {row[2]}, Publication Name: {row[3]}")
                            else:
                                print("No papers found.")
                        except ValueError as e:
                            print(e)

                    elif logged_in_choice == '3':
                        batch_update_embeddings()

                    elif logged_in_choice == '4':
                        directory = input("Enter the directory path containing PDFs: ")
                        batch_index_pdfs(directory)

                    elif logged_in_choice == '5':
                        print("Logging out.")
                        break
                    else:
                        print("Invalid option. Please try again.")

            else:
                print("Invalid username or password.")

        elif choice == '3':
            file_path = input("Enter the path of the PDF file to upload: ")
            upload_pdf(file_path)

        elif choice == '4':
            keyword = input("Enter a keyword or author name to search: ")
            search_type = input("Type 'semantic' for semantic search or 'tfidf' for TF-IDF search: ").strip().lower()
            if search_type == 'semantic':
                try:
                    results = semantic_search(keyword)
                    if results:
                        for row in results:
                            print(f"Title: {row[0]}, Author: {row[1]}, Publication Date: {row[2]}, Publication Name: {row[3]}")
                    else:
                        print("No papers found.")
                except ValueError as e:
                    print(e)
            elif search_type == 'tfidf':
                results = search_tfidf(keyword)
                if results:
                    for row in results:
                        print(f"Title: {row[0]}, Author: {row[1]}, Publication Date: {row[2]}, Publication Name: {row[3]}")
                else:
                    print("No papers found.")
            else:
                print("Invalid search type.")

        elif choice == '5':
            batch_update_embeddings()

        elif choice == '6':
            directory = input("Enter the directory path containing PDFs: ")
            batch_index_pdfs(directory)

        elif choice == '7':
            print("Exiting the application.")
            break

        else:
            print("Invalid option. Please try again.")

if __name__ == "__main__":
    main()

!apt-get install git

!git config --global user.email "sahejpreetkaur0297@gmail.com"
!git config --global user.name "sahejpreetkaur"

!git clone https://github.com/sahejpreetkaur/Research-Paper-Manager.git