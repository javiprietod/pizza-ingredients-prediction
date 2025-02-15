import pandas as pd
import os, sys, time, signal, warnings, json
import numpy as np
from datetime import datetime
import re
import random
import matplotlib.pyplot as plt
warnings.filterwarnings('ignore')

# HANDLING THE CTR+C SIGNAL
def handle_exit(signal, frame):
    
    print('Exiting', end='', flush=True)
    for _ in range(10):

        print('.', end='', flush=True)
        time.sleep(0.15)
    sys.exit(0)

signal.signal(signal.SIGINT, handle_exit)


# ETL 
def extract():
    # We read the data from the different csv files.
    # To know more about the data, check the README.md file
    orders = pd.read_csv('code/data/orders_formatted/order_details.csv', sep=';')
    df_orders = pd.read_csv('code/data/orders_formatted/orders.csv', sep=';')
    df_ingredients = pd.read_csv('code/data/pizza_types.csv',encoding = "ISO-8859-1")
    df_pizzas = pd.read_csv('code/data/pizzas.csv')


    # dtypes of each dataset to json
    types = {'object': 'str', 'int64': 'int', 'float64': 'float', 'datetime64[ns]': 'datetime'}
    df_list = [orders, df_orders, df_ingredients, df_pizzas]
    df_names = ['order_details.csv', 'orders.csv', 'pizza_types.csv', 'pizzas.csv']
    dtypes = {'dtypes': {}}
    print('INFORME DE CALIDAD DE DATOS')
    for dataset in range(len(df_list)):
        print(df_names[dataset]+':')
        print(df_list[dataset].dtypes)
        dtypes['dtypes'][df_names[dataset]] = df_list[dataset].dtypes.apply(lambda x: types[x.name]).to_dict()
    file = open('code/resources_created/dtypes.json', 'w')
    json.dump(dtypes, file)

    return orders, df_orders, df_ingredients, df_pizzas

def transform(orders: pd.DataFrame, df_orders: pd.DataFrame, df_ingredients: pd.DataFrame, df_pizzas: pd.DataFrame):

    #date to datetime
    for date in range(len(df_orders['date'])):
        try:
            df_orders['date'][date] = pd.to_datetime(df_orders['date'][date], errors='ignore').date()
        except:
            df_orders['date'][date] = datetime.fromtimestamp(float(df_orders['date'][date])).date()
    
    df_orders = df_orders[df_orders['date'].isnull() == False]
    df_orders.sort_values(by=['date','order_id'], inplace=True)
    orders = orders[orders['pizza_id'].isnull() == False]


    # Getting the sizes of each pizza
    pizza_id = []
    pizza_type = []
    for pizza in list(orders['pizza_id']):
        pizza = pizza.replace('@', 'a').replace('3', 'e').replace('0', 'o')
        temp = re.split('[\_\-\s]',pizza)
        pizza_type.append(temp[-1].upper())
        temp.remove(temp[-1])
        pizza_id.append('_'.join(temp))
    orders['pizza_id'] = pizza_id
    orders['pizza_size'] = pizza_type

    quantity = []
    for i in orders['quantity']: 
        if i != '1' and i != 'One' and i != 'one' and type(i) != float and i != '-1' and i != '2' and i != '3' and i != 'two' and i != '4' and i != '-2':
            print(i)
        if type(i) != float:       
            i = i.replace('One', '1').replace('one', '1').replace('two', '2').replace('three', '3').replace('four', '4')
            i = abs(int(i))
        else:
            i = 1 # if the quantity is null, we assume it's 1 because it's the most common case (calculated with the mean)
        quantity.append(i)
    orders['quantity'] = quantity



    # Merging datasets
    orders = orders.groupby('order_id').agg(list)
    orders = orders.drop(columns=['order_details_id'])
    orders = orders.merge(df_orders, on='order_id')
    orders = orders.drop(columns=['order_id'])


    # Ordering values by date
    pizza_orders = orders[['pizza_id','quantity', 'pizza_size','date']]
    pizza_orders = pizza_orders.groupby('date').sum().sort_values(by='date')


    # Grouping pizzas by type

    # Getting the ingredients for each pizza size
    ingredients = []
    sizes= {'S':1, 'M':1.5, 'L':2, 'XL':2.5, 'XXL':3}

    for day in range(len(pizza_orders['pizza_id'])):
        pizza_list = pizza_orders['pizza_id'][day]

        temp1 = []
        temp2 = []
        temp3 = []

        for i in range(len(pizza_list)):
            if pizza_list[i] not in temp1 or (pizza_list[i] in temp1 and temp3[temp1.index(pizza_list[i])]) != pizza_orders['pizza_size'][day][i]:
                temp1.append(pizza_list[i])
                temp2.append(pizza_orders['quantity'][day][i])
                temp3.append(pizza_orders['pizza_size'][day][i])
            else:
                temp2[temp1.index(pizza_list[i])] += pizza_orders['quantity'][day][i]
        
        # Getting the ingredients for each day
        day_ingredients = {}
        for pizza in range(len(pizza_list)):
            t = list(df_ingredients[df_ingredients['pizza_type_id'] == pizza_list[pizza]]['ingredients'])[0]
            for i in t.split(', '):
                if i in day_ingredients:
                    day_ingredients[i] += sizes[pizza_orders['pizza_size'][day][pizza]]*temp2[temp1.index(pizza_list[pizza])]
                else:
                    day_ingredients[i] = sizes[pizza_orders['pizza_size'][day][pizza]]*temp2[temp1.index(pizza_list[pizza])]
            for key,value in day_ingredients.items():
                day_ingredients[key] = int(round(value, 0))
        ingredients.append(day_ingredients)
    

        pizza_orders['pizza_id'][day] = temp1
        pizza_orders['quantity'][day] = temp2
        pizza_orders['pizza_size'][day] = temp3
        

    pizza_orders['ingredients'] = ingredients
    

    # Getting the week number of each day
    week = []
    for i in range(len(pizza_orders)):
        doy = pizza_orders.iloc[i].name.timetuple().tm_yday
        w = (doy) // 7
        week.append(w)
    pizza_orders['week'] = week
    pizza_orders.insert(0, 'week', pizza_orders.pop('week'))

    # We take all the ingredients and put them in a list
    total_ingredients = []
    for i in df_ingredients['ingredients']:
        total_ingredients += i.split(', ')
    total_ingredients = list(set(total_ingredients))
    ingredients_w = ingredients_per_week(pizza_orders)
    return pizza_orders, total_ingredients, ingredients_w
    
def load(pizza_orders, total_ingredients, ingredients_w):
    pizza_orders.to_csv('code/resources_created/pizza_orders.csv')
    weekly_ing = prediction_week(total_ingredients, ingredients_w)
    return weekly_ing

def merge_data(pizza_orders, total_ingredients, ingredients_w):
    import orders_2015 as o15
    ords15 = o15.main()
    all_orders = pd.concat([ords15,pizza_orders])
    all_orders['date'] = all_orders.index

    all_orders.drop(columns=['week'], inplace=True)
    week = []
    for i in range(len(all_orders)):
        doy = all_orders.iloc[i].name.timetuple().tm_yday
        if all_orders['date'][i].year == 2015:
            w = (doy-1) // 7
        else:
            w = (doy) // 7 + 52
        
        week.append(w)
    all_orders['week'] = week
    all_orders.insert(0, 'week', all_orders.pop('week'))
    all_orders.set_index('date', inplace=True)
    

    ingredients_w = ingredients_per_week(all_orders)
    return all_orders, total_ingredients, ingredients_w

# PLOTTING THE DATA
def ingredients_per_week(pizza_orders: pd.DataFrame):
    # Creating a list of dictionaries with the ingredients and their quantities per week

    ingredients_w = []
    for week in range(pizza_orders['week'].max()+1):
        ingredients_w.append({})
        for day in pizza_orders[pizza_orders['week']==week].iterrows(): 
            for key, value in day[1]['ingredients'].items():
                if key in ingredients_w[week]:
                    ingredients_w[week][key] += value
                else:
                    ingredients_w[week][key] = value
    return ingredients_w


def graphing_ingredients_week(total_ingredients: list, weekly_ing: list, week: int):
    # graph of ingredients per week
    plt.figure(figsize=(30,42))
    plt.xlabel('Weeks')
    plt.ylabel('Quantity')
    plt.title('Ingredients to order in week {}'.format(week))
    x = np.array(total_ingredients)
    y = np.array([weekly_ing[i][week] for i in total_ingredients])
    order = {}
    for i in range(len(x)):
        order[x[i]] = y[i]
    order = sorted(order.items(), key=lambda x: x[1], reverse=False)
    x = [i[0] for i in order]
    y = [i[1] for i in order]
    plt.barh(x, y, color='green')
    plt.savefig(f'code/resources_created/week_{week}.png')


def prediction_week(total_ingredients: list, ingredients_w: list):
    #Initialize the stock for each ingredient
    stock = {}
    for i in total_ingredients:
        stock[i] = [0,0] # [quantity left, average consumption per week]

    # For plotting a random ingredient
    x_axis = np.array(range(len(ingredients_w)))
    stock_ing1 = []
    stock_ing2 = []
    stock_ing3 = []
    ing1 = random.randint(0, len(total_ingredients)-1)
    ing2 = random.randint(0, len(total_ingredients)-1)
    ing3 = random.randint(0, len(total_ingredients)-1)

    weekly_ing = pd.DataFrame()
    weekly_ing['week'] = range(len(ingredients_w))
    for i in total_ingredients:
        weekly_ing[i] = [0 for _ in range(len(ingredients_w))]

    # An example of how we would predict for more data
    for week in range(len(ingredients_w)):
        for i in range(len(total_ingredients)):
            # We update the average of all the weeks before 
            stock[total_ingredients[i]][1] = stock[total_ingredients[i]][1]*week + ingredients_w[week][total_ingredients[i]]
            stock[total_ingredients[i]][1] = stock[total_ingredients[i]][1]/(week+1)
            if week == 0:
                stock[total_ingredients[i]][1] = int(ingredients_w[week][total_ingredients[i]]*1.2)

            # The week passes and ingredients are taken
            stock[total_ingredients[i]][0] -= ingredients_w[week][total_ingredients[i]]

            # The stock is updated to 1.6 times the average of the past weeks
            p = 1.6 - stock[total_ingredients[i]][0]/stock[total_ingredients[i]][1]
            stock[total_ingredients[i]][0] += stock[total_ingredients[i]][1]*p # adding the stock for the next week
            
            # For graphing
            weekly_ing[total_ingredients[i]][week] = round(stock[total_ingredients[i]][1]*p)
            if i == ing1:
                stock_ing1.append(stock[total_ingredients[ing1]][0])
            if i == ing2:
                stock_ing2.append(stock[total_ingredients[ing2]][0])
            if i == ing3:
                stock_ing3.append(stock[total_ingredients[ing3]][0])

    # Graph of stock of one random ingredient
    plt.figure(figsize=(14,5))
    
    plt.xlabel('Weeks')
    plt.ylabel('Quantity')
    ing1 = total_ingredients[ing1]
    plt.title(f'{ing1}\' stock over the weeks')
    x = np.array(range(len(ingredients_w)))
    y1 = np.array([ingredients_w[i][ing1] for i in range(len(ingredients_w))])
    plt.ylim(0, y1.max()*1.7)
    plt.plot(x_axis, stock_ing1, label=f'stock of {ing1}')
    plt.plot(x, y1, label=ing1)
    plt.legend()
    plt.savefig(f'code/resources_created/{ing1}.png')
    plt.close()

    plt.figure(figsize=(14,5))
    plt.xlabel('Weeks')
    plt.ylabel('Quantity')
    ing2 = total_ingredients[ing2]
    plt.title(f'{ing2}\' stock over the weeks')
    x = np.array(range(len(ingredients_w)))
    y2 = np.array([ingredients_w[i][ing2] for i in range(len(ingredients_w))])
    plt.ylim(0, y2.max()*1.7)
    plt.plot(x_axis, stock_ing2, label=f'stock of {ing2}')
    plt.plot(x, y2, label=ing2)
    plt.legend()
    plt.savefig(f'code/resources_created/{ing2}.png')
    plt.close()

    plt.figure(figsize=(14,5))
    plt.xlabel('Weeks')
    plt.ylabel('Quantity')
    ing3 = total_ingredients[ing3]
    plt.title(f'{ing3}\' stock over the weeks')
    x = np.array(range(len(ingredients_w)))
    y3 = np.array([ingredients_w[i][ing3] for i in range(len(ingredients_w))])
    plt.ylim(0, y3.max()*1.7)
    plt.plot(x_axis, stock_ing3, label=f'stock of {ing3}')
    plt.plot(x, y3, label=ing3)
    plt.legend()
    plt.savefig(f'code/resources_created/{ing3}.png')
    plt.close()

    weekly_ing.set_index('week', inplace=True)
    weekly_ing.to_csv('code/resources_created/weekly_ing.csv')

    return weekly_ing

if __name__ == '__main__':
    os.mkdir('code/resources_created') if not os.path.exists('code/resources_created') else None
    orders, df_orders, df_ingredients, df_pizzas = extract()
    pizza_orders, total_ingredients, ingredients_w  = transform(orders, df_orders, df_ingredients, df_pizzas)
    all_orders, total_ingredients, ingredients_w = merge_data(pizza_orders, total_ingredients, ingredients_w)
    weekly_ing = load(all_orders, total_ingredients, ingredients_w)
    graphing_ingredients_week(total_ingredients, weekly_ing, 104)
    os.system('clear||cls')

    # Get the prediction for a week in 2015 or 2016
    wish = ''
    while wish != 'y' or wish != 'n':
        wish = input('Do you wish to know what to order for the next week (y/n)? ')
        if wish == 'y':
            print('What is today\'s date?')
            date = input('Enter a date in the format YYYY-MM-DD: ')
            
            # If the year is 2015 or 2016, we can predict, if not, we can't
            if date.split('-')[0] != '2015' and date.split('-')[0] != '2016':
                print('Year not valid')
                continue
            # If the date is not valid, we can't predict
            try:
                date = datetime.strptime(date, '%Y-%m-%d')
            except:

                print('Wrong date format')
                continue

            doy = date.timetuple().tm_yday
            if date.year == 2015:
                w = (doy-1) // 7
            else:
                w = (doy) // 7 + 52
            with open(f'resources_created/order-w{w}.txt','w') as f:
                for ingredient in weekly_ing.columns:
                    f.write(f'{ingredient}: {weekly_ing[ingredient][w]}\n')
                    
                print('The order has been saved in the file order.txt')
                f.close()
        elif wish == 'n':
            exit()
        else:
            print('Please enter a valid input')

