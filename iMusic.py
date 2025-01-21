
import csv
import sqlite3
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for
)

app = Flask(__name__)

UPLOAD_FOLDER = Path.cwd() / 'uploads'
DB_FILE = Path.cwd() / 'data/iMusic.db'


####################
# Routes
####################

@app.route('/', methods=['GET'])
def index():

    return render_template('index.html')

@app.route('/upload/', methods=['GET', 'POST'])
def upload_route():

    if request.method == 'POST':
        # Retrieve the uploaded file
        file = request.files.get('file')
        if not file:
            flash('No file selected. Please upload a valid file.', 'warning')
            return redirect(url_for('upload_route'))

        # Define the path to save the uploaded file
        uploaded_file_path = UPLOAD_FOLDER / 'Customers.tsv'

        try:
            # Ensure the upload folder exists
            UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
            
            # Save the uploaded file
            file.save(uploaded_file_path)
            flash('File uploaded successfully.', 'success')

            # Update the database with the uploaded file
            update_customers(uploaded_file_path)
            flash('Customers updated successfully.', 'success')
        except Exception as e:
            # Handle errors during file saving or database update
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('upload_route'))

        # Redirect to the home page after successful upload
        return redirect(url_for('index'))

    # Render the upload page for GET requests
    return render_template('upload.html')

@app.route('/statistics/', methods=['GET', 'POST'])
def statistics():

    if request.method == 'POST':
        country = request.form.get('country')
        stats = get_statistics(country)
        return render_template('statistics.html', stats=stats)
    

    countries = get_all_countries()
    return render_template('statistics.html', countries=countries)


@app.route('/invoice/', methods=['GET'])
def invoice():

    customers = get_all_customers()
    albums = get_all_albums()
    return render_template('invoice.html', customers=customers, albums=albums)

@app.route('/generate_invoice/', methods=['POST'])
def generate_invoice():

    customer_id = request.form.get('customer_id')
    selections = request.form.getlist('albums')
    address = request.form.get('address')
    city = request.form.get('city')
    country = request.form.get('country')
    postal_code = request.form.get('postal_code')

    if not customer_id or not selections:
        flash('Invalid customer or album selected', 'danger')
        return redirect(url_for('invoice'))

    process_invoice_in_db(customer_id, selections, address, city, country, postal_code)
    flash('Invoice generated successfully', 'success')


    return render_template('invoice.html')

@app.errorhandler(404)
def page_not_found(e):

    return render_template('error.html', messages=['404: Page not found.']), 404


####################
# Functions
####################

def update_customers(customer_tsv_file):

    try:
        connection = sqlite3.connect(DB_FILE)
        cursor = connection.cursor()

        # Open and read the TSV file
        with open(customer_tsv_file, 'r') as f:
            reader = csv.reader(f, delimiter='\t')  # Assuming TSV file, tab-delimited
            for row in reader:

                    cursor.execute('''
                        INSERT OR REPLACE INTO Customer (CustomerId, FirstName, LastName, Email, Country, City, Address, PostalCode)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]))  # Adjust columns as per your TSV
        connection.commit()
        connection.close()
        flash('Customers updated successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred while updating customers: {str(e)}', 'danger')


def get_all_countries():

    try:
        connection = sqlite3.connect(DB_FILE)
        cursor = connection.cursor()
        cursor.execute('SELECT DISTINCT Country FROM Customer')
        countries = cursor.fetchall()
        connection.close()
        return [country[0] for country in countries]
    except Exception as e:
        raise Exception(f"Error retrieving countries: {str(e)}")


def get_statistics(country):

    try:
        connection = sqlite3.connect(DB_FILE)
        cursor = connection.cursor()

        if country:
            cursor.execute('''
                SELECT COUNT(DISTINCT Customer.CustomerId), SUM(Invoice.Total)
                FROM Invoice
                JOIN Customer ON Customer.CustomerId = Invoice.CustomerId
                WHERE Customer.Country = ?
            ''', (country,))
        else:
            cursor.execute('''
                SELECT COUNT(DISTINCT Customer.CustomerId), SUM(Invoice.Total)
                FROM Invoice
            ''')


        stats = cursor.fetchone()
        connection.close()
        return stats

    except Exception as e:
        raise Exception(f"Error retrieving statistics: {str(e)}")

def get_all_customers():

    try:
        connection = sqlite3.connect(DB_FILE)
        cursor = connection.cursor()
        cursor.execute('''
            SELECT CustomerId, FirstName, LastName
            FROM Customer
            ORDER BY FirstName, LastName
        ''')
        customers = cursor.fetchall()
        connection.close()
        return [
            {'CustomerId': customer[0], 'FullName': f"{customer[1]} {customer[2].upper()}"}
            for customer in customers
        ]
    except Exception as e:
        raise Exception(f"Error retrieving customers: {str(e)}")


def get_all_albums():
 
    try:
        connection = sqlite3.connect(DB_FILE)
        cursor = connection.cursor()
        cursor.execute('''
            SELECT Album.AlbumId, Album.Title, Artist.Name, SUM(Track.UnitPrice)
            FROM Album
            JOIN Artist ON Album.ArtistId = Artist.ArtistId
            JOIN Track ON Album.AlbumId = Track.AlbumId
            GROUP BY Album.AlbumId
            ORDER BY Artist.Name, Album.Title
        ''')
        albums = cursor.fetchall()
        connection.close()
        return [
            {
                'AlbumId': album[0],
                'Title': album[1],
                'Artist': album[2],
                'Price': round(album[3], 2)
            }
            for album in albums
        ]
    except Exception as e:
        raise Exception(f"Error retrieving albums: {str(e)}")


def process_invoice_in_db(customer_id, selections, address, city, country, postal_code):

    try:
        connection = sqlite3.connect(DB_FILE)
        cursor = connection.cursor()

        # Create the invoice
        cursor.execute('''
            INSERT INTO Invoice (CustomerId, InvoiceDate, BillingAddress, BillingCity, BillingCountry, BillingPostalCode)
            VALUES (?, DATETIME('now'), ?, ?, ?, ?)
        ''', (customer_id, address, city, country, postal_code))

        # Get the last inserted InvoiceId
        invoice_id = cursor.lastrowid

        # Link the selected albums to the invoice
        for album_id in selections:
            cursor.execute('''
                INSERT INTO InvoiceLine (InvoiceId, TrackId, UnitPrice, Quantity)
                SELECT ?, TrackId, UnitPrice, 1
                FROM Track
                WHERE AlbumId = ?
            ''', (invoice_id, album_id))

        connection.commit()
        connection.close()
    except Exception as e:
        raise Exception(f"Error processing invoice: {str(e)}")



####################
# Main
####################

def main():

    app.secret_key = 'I love dbi'  
    app.run(debug=True, port=5000)


if __name__ == '__main__':
    main()