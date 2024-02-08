from flask import Flask,request,render_template,redirect,session
from flask_mysqldb import MySQL
import yaml
import numpy as np
import pickle
import pandas as pd
from flask_bcrypt import Bcrypt
import MySQLdb.cursors

# importing model
model = pickle.load(open('new_model.pickle','rb'))   #for crop prediction
model_fertilizer = pickle.load(open('modelfertilizer.pkl','rb'))  #for fertilizer prediction

# creating flask app
app = Flask(__name__)
bcrypt = Bcrypt(app)  #for password hashing

#configuring the db
app.secret_key = 'abc123!@#'
db = yaml.safe_load(open('db.yaml'))
app.config['MYSQL_HOST'] = db['mysql_host']
app.config['MYSQL_USER'] = db['mysql_user']
app.config['MYSQL_PASSWORD'] = db['mysql_password']
app.config['MYSQL_DB'] = db['mysql_db']

mysql = MySQL(app)


#login page
@app.route('/')
@app.route('/login',methods=['GET','POST'])
def login():
    message = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']
        
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute('SELECT * FROM users WHERE username = %s ', (username,))
        user = cur.fetchone()
        
        if user and bcrypt.check_password_hash(user['password'],password):
            session['Loggedin'] = True
            session['userID'] = user['userID']
            session['username'] = user['username']
            message = 'Logged in successfully'
            return render_template('index.html',message=message)
        else:
            message = "incorrect username or password!!"
            
    return render_template('login.html',message=message)
#log out 
@app.route('/logout')
def logout():
    session.pop('Loggedin',None)
    session.pop('userID',None)
    session.pop('username',None)
    return redirect('/login')

#register page
@app.route('/register', methods=['GET', 'POST'])
def register():
    message = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        account = cur.fetchone()

        if account:
            message = 'Username already exists!'
        elif not username or not password:
            message = 'Please fill out the form!'
        else:
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')  #encrpyt the password
            cur.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, hashed_password))
            mysql.connection.commit()
            message = 'You have successfully registered!'
    
    elif request.method == 'POST':
        message = 'Please fill out the form!'

    return render_template('register.html', message=message)



def index():
    return render_template("index.html")

#display the result
@app.route('/dashboard')
def users():
    cur = mysql.connection.cursor()
    userID = session.get('userID', None)
    
    #query to show data
    query = """
    SELECT
        users.userID,
        users.username,
        crop_prediction.predicted_crop,
        crop_prediction.predicted_fertilizer,
        crop_prediction.date AS prediction_date
    FROM
        users
    JOIN
        crop ON users.userID = crop.userID
    LEFT JOIN
        crop_prediction ON users.userID = crop_prediction.userID
    WHERE
        users.userID = %s;
"""
    resultValue = cur.execute(query,(userID,))
    if resultValue > 0:
        userDetails = cur.fetchall()
        return render_template('dashboard.html',userDetails=userDetails)



#fetching data from the page and predicting the crop

@app.route("/predict",methods=['POST'])
def predict():
    N = request.form['Nitrogen']
    P = request.form['Phosporus']
    K = request.form['Potassium']
    temp = request.form['Temperature']
    humidity = request.form['Humidity']
    ph = request.form['Ph']
    rainfall = request.form['Rainfall']
    soil_color = request.form['Soil_color']

    soil_col = {
        'red': 0,
        'dark brown': 1,
        'medium brown': 2,
        'reddish brown': 3, 
        'black': 4, 
        'light brown': 5,
    }
    soil_color_lower = soil_color.lower()
    if soil_color_lower in soil_col:
        soil_color_num = soil_col[soil_color_lower]

    userID = session.get('userID', None)

    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO CROP(userID, nitrogen, phosphor, potassium, temperature, humidity, ph, rainfall, soil_color, date) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())",
        (userID, N, P, K, temp, humidity, ph, rainfall, soil_color)
    )
    mysql.connection.commit()
    cur.close()

    crop_result = predict_crop(N, P, K, temp, humidity, ph, rainfall)
    fertilizer_result = predict_fertilizer(soil_color_num, N, P, K, ph, rainfall, temp)

    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO crop_prediction (userID, predicted_crop, predicted_fertilizer, date) VALUES (%s, %s, %s, NOW())",
        (userID, crop_result, fertilizer_result)
    )
    mysql.connection.commit()
    cur.close()

    action = request.form.get('action')
    if action == 'crop':
        # crop_result = predict_crop(N, P, K, temp, humidity, ph, rainfall)
        return render_template('index.html', crop_result=crop_result)
    elif action == 'fertilizer':
        # fertilizer_result = predict_fertilizer(soil_color_num, N, P, K, ph, rainfall, temp)
        return render_template('index.html', fertilizer_result=fertilizer_result)
    else:
        return render_template('index.html', error="Please select an action (Crop or Fertilizer)")


def predict_crop(N, P, K, temp, humidity, ph, rainfall):
    feature_list = [N, P, K, temp, humidity, ph, rainfall]
    single_pred = np.array(feature_list).reshape(1, -1)
    prediction = model.predict(single_pred)
    crop_dict = {0: 'apple', 1: 'banana', 2: 'blackgram', 3: 'chickpea', 4: 'coconut', 5: 'coffee', 
                 6: 'cotton', 7: 'grapes', 8: 'jute', 9: 'kidneybeans', 10: 'lentil', 11: 'maize', 
                 12: 'mango', 13: 'mothbeans', 14: 'mungbean', 15: 'muskmelon', 16: 'orange',
                 17: 'papaya', 18: 'pigeonpeas', 19: 'pomegranate', 20: 'rice', 21: 'watermelon'}
    if prediction[0] in crop_dict:
        return crop_dict[prediction[0]]
    else:
        return "Sorry, we could not determine the best crop to be cultivated with the provided data."

def predict_fertilizer(soil_color_num, N, P, K, ph, rainfall, temp):
    feature_list_fertilizer = [soil_color_num, N, P, K, ph, rainfall, temp]
    single_pred_fertilzer = np.array(feature_list_fertilizer).reshape(1, -1)
    prediction_fertilizer = model_fertilizer.predict(single_pred_fertilzer)
    fertilizer_dict = {0: 'Ferrous Sulphate', 1: 'Ammonium Sulphate', 2: 'SSP', 3: 'MOP', 4: 'DAP', 5: 'Sulphur', 
             6: 'Urea', 7: '10:10:10 NPK', 8: 'Hydrated Lime', 9: '10:26:26 NPK', 10: '50:26:26 NPK', 11: '18:46:00 NPK', 
             12: '19:19:19 NPK', 13: '12:32:16 NPK', 14: 'Magnesium Sulphate', 15: 'White Potash', 
             16: 'Chilated Micronutrient', 17: '13:32:26 NPK', 18: '20:20:20 NPK'}
    if prediction_fertilizer[0] in fertilizer_dict:
        return fertilizer_dict[prediction_fertilizer[0]]
    else:
        return "Sorry, we could not determine the best fertilizer to be used with the provided data."



# python main
if __name__ == "__main__":
    app.run(debug=True)