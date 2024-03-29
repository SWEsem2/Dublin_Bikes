import pickle
from keras.models import load_model
import pandas as pd
import numpy as np
import requests
import json
from datetime import datetime, timedelta
import os
import sys
from dotenv import load_dotenv
load_dotenv()


script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.append(project_root)

def round_nearest(value):
    integer_part = int(value)
    fractional_part = value - integer_part
    if fractional_part >= 0.5:
        return integer_part + 1
    else:
        return integer_part

def predict_range_from_weather(id, start, end):
    model_path = f"models/ava_weather/ANN.keras"
    scaler_path = f"models/ava_weather/preprocessors.pkl"
    model = load_model(model_path)
    with open(scaler_path, 'rb') as model_file:
        model_data = pickle.load(model_file)

    preprocessor = model_data['preprocessor']
    scalar = model_data['scaler']
    output = predict_range(id, start, end, preprocessor, scalar, model)

    return output

def predict_range(id, start, end, preprocessor, scalar, model):
    link = 'http://api.weatherapi.com/v1/forecast.json'
    api = os.getenv('weather_api')
    contract = 'Dublin'

    start = datetime.strptime(start, "%Y-%m-%d")
    end = datetime.strptime(end, "%Y-%m-%d")
    date_list = []
    delta = end - start
    for i in range(delta.days + 1):
        current_date = start + timedelta(days=i)
        date_list.append(current_date.strftime("%Y-%m-%d"))

    stands = []
    bikes = []
    for date in date_list:
        response = requests.get(link, 
                                params={"key": api, 
                                        "q": contract,
                                        'dt': date})
        response.raise_for_status()
        data = response.text
        data = json.loads(data)
        data = pd.json_normalize(data['forecast']['forecastday'][0])
        sample = pd.DataFrame()
        sample['time_stamp'] = pd.to_datetime(data['date_epoch']).dt.round('h')
        sample['maxtemp_c'] = data['day.maxtemp_c']
        sample['mintemp_c'] = data['day.mintemp_c']
        sample['avgtemp_c'] = data['day.avgtemp_c']
        sample['maxwind_kph'] = data['day.maxwind_kph']
        sample['totalprecip_mm'] = data['day.totalprecip_mm']
        sample['avgvis_km'] = data['day.avgvis_km']
        sample['avghumidity'] = data['day.avghumidity']
        sample['uv'] = data['day.uv']
        sample['sunrise'] = pd.to_datetime(data['astro.sunrise'], format='%I:%M %p')
        sample['sunrise'] = sample['sunrise'].apply(lambda x: x.hour * 3600 + x.minute * 60 + x.second)
        sample['sunset'] = pd.to_datetime(data['astro.sunset'], format='%I:%M %p')
        sample['sunset'] = sample['sunset'].apply(lambda x: x.hour * 3600 + x.minute * 60 + x.second)
        sample['uv'] = data['day.uv']
        sample['id'] = [id]
        sample['date_only'] = sample['time_stamp'].dt.day
        sample['day_of_week'] = sample['time_stamp'].dt.dayofweek
        sample = sample.drop('time_stamp', axis=1)
        input_data_processed = preprocessor.transform(sample)
        predicted_scaled = model.predict(input_data_processed.toarray())
        predicted = scalar.inverse_transform(predicted_scaled)
        bikes.append(round_nearest(predicted[0][0]))
        stands.append(round_nearest(predicted[0][1]))

    output = {
        'bikes' : bikes,
        'stands' : stands
    }

    return output

def predict_hourly_from_weather(id, date, start, end):
    model_path = f"models/ava_weather/RNN/rnn_{id}.keras"
    scaler_path = f"models/ava_weather/RNN/model_data/scaler_{id}.pkl"
    model = load_model(model_path)
    with open(scaler_path, 'rb') as model_file:
        model_data = pickle.load(model_file)

    preprocessor = model_data['scaler_X']
    scalar = model_data['scaler_y']
    output = predict_hourly(date, start, end, preprocessor, scalar, model)
    return output

def predict_hourly(date, start, end, preprocessor, scalar, model):
    link = 'http://api.weatherapi.com/v1/forecast.json'
    api = os.getenv('weather_api')
    contract = 'Dublin'
    response = requests.get(link, 
                                params={"key": api, 
                                        "q": contract,
                                        'dt': date})
    response.raise_for_status()
    data = response.text
    data = json.loads(data)
    data = pd.json_normalize(data['forecast']['forecastday'][0]['hour'])
    data['time'] = pd.to_datetime(data['time']).round('h')

    start = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{date} {end}", "%Y-%m-%d %H:%M")
    datetime_list = []
    current_datetime = start
    while current_datetime <= end:
        datetime_list.append(str(current_datetime.strftime("%Y-%m-%d %H:%M")))
        current_datetime += timedelta(hours=1)

    stands = []
    bikes = []

    for dtime in datetime_list:
        sample = data[data['time'] == dtime]
        sample = sample[['time', 'temp_c', 'feelslike_c', 'wind_kph', 'humidity', 'precip_mm', 'gust_kph', 'wind_degree', 'pressure_mb', 'cloud', 'uv']]
        sample = sample.rename(columns={'time': 'time_stamp'})
        sample.set_index('time_stamp', inplace=True)
        input_data_processed = preprocessor.transform(sample)
        input_data_processed = np.reshape(input_data_processed, (1, input_data_processed.shape[0], input_data_processed.shape[1]))
        predicted_scaled = model.predict(input_data_processed)
        predicted = np.vectorize(round_nearest)(scalar.inverse_transform(predicted_scaled))
        bikes.append(int(predicted[0][0]))
        stands.append(int(predicted[0][1]))
        
    output = {
        'bikes' : bikes,
       'stands' : stands
    }

    return output