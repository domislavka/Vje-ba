
# coding: utf-8

# In[1]:


from __future__ import print_function
import warnings
from os import environ
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter('ignore', Image.DecompressionBombWarning)
environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from keras.applications import vgg16
from keras.layers import Dense, Conv2D, BatchNormalization, Activation, MaxPooling2D
from keras.layers import GlobalAveragePooling2D, AveragePooling2D, Input, Flatten, Activation, Dropout, Dense
from keras.optimizers import Adam, SGD
from keras.initializers import glorot_normal
from keras.callbacks import ModelCheckpoint, LearningRateScheduler, TensorBoard
from keras.callbacks import ReduceLROnPlateau
from keras.preprocessing.image import ImageDataGenerator, array_to_img, img_to_array, load_img
from keras.regularizers import l2
from keras import backend as K
from keras.models import Sequential, Model
from os import path, getcwd
import pandas as pd
import random
import numpy as np
import shutil
from time import time

# In[2]:


def sve_jpg(df):
    for item in list(df.new_filename):
        if not '.jpg' in item:
            return False
    return True


# In[3]:


df = pd.read_csv(path.join(getcwd(), 'all_data_info.csv'))
seed = 123

print(df.shape)
df.head()


# In[4]:


print('Sve su jpg: ' + str(sve_jpg(df)))


# In[5]:


threshold = 200

x = list(df['artist'].value_counts())
# broj umjetnika koji imaju vise ili jednako od 300 slika
print(len([a for a in x if a >= threshold]))
# len(set(x)) #---> ukupan broj umjetnika


# In[6]:


# train, validation, test --- 80, 10, 10
num_train = 160
num_val = 20
num_test = num_val
num_samples = num_train + num_val + num_test
b_size = 60

#lista umjetnika koje ćemo promatrati
temp = df['artist'].value_counts()
artists = temp[temp >= threshold].index.tolist()
# print(artists)

num_artists = len(artists)
print('Prepoznajemo ' + str(num_artists) + ' umjetnika')


# In[7]:

"""
train_dfs = []
val_dfs = []
test_dfs = []

for a in artists:
    # PROVJERI KASNIJE ŠTA JE S NA=TRUE
    tmp = df[df['artist'].str.startswith(a)].sample(n=num_samples, random_state=seed)
    # print(tmp.shape)
    t_df = tmp.sample(n=num_train, random_state=seed)
    rest_df = tmp.loc[~tmp.index.isin(t_df.index)] # uzmi komplement od t_df
    # print(rest_df.shape)
    v_df = rest_df.sample(n=num_val, random_state=seed)
    te_df = rest_df.loc[~rest_df.index.isin(v_df.index)]
    
    train_dfs.append(t_df)
    val_dfs.append(v_df)
    test_dfs.append(te_df)
    
    # ovo se pokrene samo jednom!!
    copyImagesToFiles(a, t_df, v_df, te_df)

train_df = pd.concat(train_dfs)
val_df = pd.concat(val_dfs)
test_df = pd.concat(test_dfs)

print('train tablica\t\t', train_df.shape)
print('validation tablica\t', val_df.shape)
print('test tablica\t\t', test_df.shape)
"""
# In[162]:


def center_crop(img, center_crop_size):
    assert img.shape[2] == 3
    centerw, centerh = img.shape[0] // 2, img.shape[1] // 2
    halfw, halfh = center_crop_size[0] // 2, center_crop_size[1] // 2
    return img[centerw-halfw:centerw+halfw, centerh-halfh:centerh+halfh, :]

# https://jkjung-avt.github.io/keras-image-cropping/
def random_crop(img, random_crop_size):
    # Note: image_data_format is 'channel_last'
    assert img.shape[2] == 3
    height, width = img.shape[0], img.shape[1]
    dy, dx = random_crop_size
    x = np.random.randint(0, width - dx + 1)
    y = np.random.randint(0, height - dy + 1)
    return img[y:(y+dy), x:(x+dx), :]


def crop_generator(batches, crop_length, random_cropping=True, test_batch=False):
    '''
    Take as input a Keras ImageGen (Iterator) and generate random
    crops from the image batches generated by the original iterator
    '''
    while True:
        if test_batch == False:
            batch_x, batch_y = next(batches)
        else:
            batch_x = next(batches)
        batch_crops = np.zeros((batch_x.shape[0], crop_length, crop_length, 3))
        for i in range(batch_x.shape[0]):
            if random_cropping == True:
                batch_crops[i] = random_crop(batch_x[i], (crop_length, crop_length))
            else:
                batch_crops[i] = center_crop(batch_x[i], (crop_length, crop_length))
        if test_batch == False:
            yield (batch_crops, batch_y)
        else:
            yield batch_crops


# In[163]:


# velicina slika koje dajemo ulaznom sloju mreze
input_shape = (224, 224, 3)
# velicina batch-a
b_size = 30

train_datagen = ImageDataGenerator(
                horizontal_flip=True)

val_datagen = ImageDataGenerator(
                horizontal_flip=True)
test_datagen = ImageDataGenerator()


train_generator = train_datagen.flow_from_directory(
                    '../train200',
                    batch_size=b_size,
                    class_mode='categorical')
train_generator = train_datagen.standardize(train_generator)
# na slikama iz train skupa radimo crop na slučajnom mjestu
train_crops = crop_generator(train_generator, 224)

validation_generator = val_datagen.flow_from_directory(
                    '../validation200',
                    batch_size=b_size,
                    class_mode='categorical')
# na slikama iz validation skupa radimo centralni crop
val_crops = crop_generator(validation_generator, 224, False)

'''
test_generator = test_datagen.flow_from_directory(
                '../test200',
                batch_size=b_size,
                class_mode=None, # this means our generator will only yield batches of data, no labels
                shuffle=False) # our data will be in order

test_crops = crop_generator(test_generator, 224, False, True)
'''

tbCallBack = TensorBoard(log_dir='./GraphTransferVgg16-200', 
                         write_graph=True, 
                         write_images=True,
                         write_grads=False)

mdCheckPoint = ModelCheckpoint(filepath='transfer-vgg16-200-pretrained.h5',
                                monitor='val_acc',
                                mode='max',
                                save_best_only=True,
                                save_weights_only=False,
                                verbose=1,
                                period=1)


vgg16 = vgg16.VGG16(include_top=False, weights='imagenet')

x = vgg16.output
x = Dense(128, activation='sigmoid')(x)
x = GlobalAveragePooling2D()(x)
x = Dropout(0.2)(x)
preds_layer = Dense(num_artists, activation='softmax')(x)

transfer_vgg16_200 = Model(inputs=vgg16.input, outputs=preds_layer)

for layer in vgg16.layers:
    layer.trainable = False

transfer_vgg16_200.summary()

transfer_vgg16_200.compile(loss='categorical_crossentropy',
                     optimizer=SGD(lr=1e-3, momentum=0.9),
                     metrics=['accuracy'])

transfer_vgg16_200.fit_generator(train_crops,
                    steps_per_epoch=STEP_SIZE_TRAIN,
                    epochs=20,
                    validation_data=val_crops,
                    validation_steps=STEP_SIZE_VALID,
                    callbacks=[tbCallBack, mdCheckPoint])

# spremimo pretrained model

transfer_vgg16_200.save_weights('transfer_vgg16_test_200_tezine.h5')
transfer_vgg16_200.save('transfer_vgg16_test_200.h5')


# fine-tuning

base_model=vgg16.VGG16(include_top=False, weights='None')

i=0
for layer in base_model.layers:
    layer.trainable = True
    i = i+1
	print(i,layer.name)
	
xx = base_model.output
xx = Dense(128)(xx)
xx = GlobalAveragePooling2D()(xx)
xx = Dropout(0.3)(xx)
predictions = Dense(num_artists, activation='softmax')(xx)

tensorboard = TensorBoard(log_dir='./FineTunedGraphTransferVgg16-200')
filepath = 'vgg16-transfer-200_fine_tuned_model.h5'
checkpoint = ModelCheckpoint(filepath,
							 monitor='val_acc',
							 verbose=1,
							 save_best_only=False,
							 save_weights_only=False,
							 mode='auto',
							 period=1)

finetuned_vgg16_200 = Model(inputs=base_model.input, outputs=predictions)

finetuned_vgg16_200.load_weights("transfer-vgg16-200-pretrained.h5")

finetuned_vgg16_200.compile(loss="categorical_crossentropy",
							optimizer=optimizers.SGD(lr=0.0001, momentum=0.9),
							metrics=["accuracy"])

finetuned_vgg16_200.fit_generator(train_crops,
								  steps_per_epoch=STEP_SIZE_TRAIN,
								  epochs=20,
								  callbacks=[tensorboard, checkpoint],
								  validation_data = val_crops,
								  validation_steps=STEP_SIZE_VALID)


# spremimo finetuned model
finetuned_vgg16_200.save_weights('finetuned_transfer_vgg16_test_200_tezine.h5')
finetuned_vgg16_200.save('finetuned_transfer_vgg16_test_200.h5')

