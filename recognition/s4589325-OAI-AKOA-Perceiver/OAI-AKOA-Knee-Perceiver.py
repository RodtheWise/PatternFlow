#!/bin/python3

# General References:
# - https://keras.io/examples/vision/perceiver_image_classification/ (good resource to see general structure)
# - https://github.com/Rishit-dagli/Perceiver (decent for seeing how some functions are implemented)
# - https://keras.io/api/layers/base_layer/ (how to use classes with tf)

# ##### Setup #####

# Libraries needed for model
import tensorflow as tf
import tensorflow.keras
import tensorflow_addons as tfa
import PIL

# Libraries needed for data importing
import os
import itertools
from PIL import Image
import math
import numpy as np # just need this for a single array conversion in the preprocessing step - please don't roast me

print("Tensorflow Version:", tf.__version__)
tf.config.run_functions_eagerly(True)

# ##### Macros #####
SAVE_DATA			= False
BATCH_SIZE			= 32
TEST_TRAINING_SPLIT	= 0.8
IMG_WIDTH			= 260
IMG_HEIGHT			= 228
SEED				= 123
BANDS				= 10

# ##### Import Data #####

def save_data():
	print("Saving Data...")

	dataDirectory = '../../../AKOA_Analysis/'
	print("Data Directory:", dataDirectory)

	# Need to sort data by patient so that we aren't leaking data between training and validation sets
	allPics = [dataDirectory + f for f in os.listdir(dataDirectory)]

	patients = [[0] * 2 for _ in range(len(allPics))]
	print("Number of Patients:", len(patients))

	i = 0
	for pic in allPics:
		# Get unique id for each patient
		pic = pic.split('OAI')[1]
		baseline_num_str = pic.split('de3d1')[0].split('BaseLine')[1]
		baseline_num = int(''.join(c for c in baseline_num_str if c.isdigit()))
		pic_num = pic.split('.nii.gz_')[1].split('.')[0]
		initial_id = pic.split('_')[0] + '_BaseLine_' + str(baseline_num) + '.' + pic_num
		patients[i][0] = initial_id
		i = i + 1

	# Assign each patient left or right status (slow code)
	ii = 0
	for i in patients:
		if ('right' in allPics[ii].lower()) or ('R_I_G_H_T' in allPics[ii]):
			patients[ii][1] = 1
		else:
			patients[ii][1] = 0
		ii += 1

	print('Right Knees:', sum([i[1] for i in patients]))
	print('Left Knees:', len(patients) - sum([i[1] for i in patients]))

	# Sort by substring
	patients = [list(i) for j, i in itertools.groupby(sorted(patients))]

	# TEMPORARY: REDUCE AMOUNT OF DATA USED!
	patients = patients[0:math.floor(len(patients) * 0.01)]

	# Split data
	print("Splitting data into training and testing sets")
	patients_train	= patients[0:math.floor(len(patients) * TEST_TRAINING_SPLIT)]
	patents_test	= patients[math.floor(len(patients) * TEST_TRAINING_SPLIT):-1]

	# Remove extra axis added by the above sorting line
	patients_train	= [item for sublist in patients_train for item in sublist]
	patients_test	= [item for sublist in patents_test for item in sublist]

	# Import/Load images
	print("Importing training images")
	xtrain = []
	ytrain = []
	for i in patients_train:
		for j in allPics:
			if i[0].split('.')[0] in j and i[0].split('.')[1] in j.split('de3')[1]:
				xtrain.append(np.asarray(PIL.Image.open(j).convert("L")))
				ytrain.append(i[1])
				break
	print("Importing testing images")
	xtest = []
	ytest = []
	for i in patients_test:
		for j in allPics:
			if i[0].split('.')[0] in j and i[0].split('.')[1] in j.split('de3')[1]:
				xtest.append(np.asarray(PIL.Image.open(j).convert("L")))
				ytest.append(i[1])
				break

	# Normalize the data to [0,1]
	print("Normalizing data")
	xtrain = np.array(xtrain, dtype=float)
	xtest  = np.array(xtest, dtype=float)
	xtrain[:] /= 255
	xtest[:] /= 255

	# Save the data to local drive
	print("Saving data to disk")
	np.save('../../../xtrain', xtrain)
	np.save('../../../ytrain', ytrain)
	np.save('../../../xtest', xtest)
	np.save('../../../ytest', ytest)

# Save the data
if SAVE_DATA:
	save_data()

# Load Data
print("Loading Data")
xtrain = np.load('../../../xtrain.npy')
ytrain = np.load('../../../ytrain.npy')
xtest = np.load('../../../xtest.npy')
ytest = np.load('../../../ytest.npy')

ytest = np.squeeze(ytest)
ytrain = np.squeeze(ytrain)

''' # Cannot use this code because it leaks data between training/test sets
dataset_train = tf.keras.preprocessing.image_dataset_from_directory(
    dataDirectory,
	validation_split=0.2,
	subset="training",
	seed=SEED,
	label_mode=None,
	image_size=(IMG_WIDTH, IMG_HEIGHT),
	batch_size=BATCH_SIZE,
	color_mode='grayscale'
)
dataset_validation = tf.keras.preprocessing.image_dataset_from_directory(
    dataDirectory,
	validation_split=0.2,
	subset="validation",
	seed=SEED,
	label_mode=None,
	image_size=(IMG_WIDTH, IMG_HEIGHT),
	batch_size=BATCH_SIZE,
	color_mode='grayscale'
)
'''

def pos_encoding(img, bands, Fs):
	# Create grid
	n, x_size, y_size = img.shape
	x = tf.linspace(-1, 1, x_size)
	y = tf.linspace(-1, 1, y_size)
	xy_mesh = tf.meshgrid(x,y)
	xy_mesh = tf.transpose(xy_mesh)
	xy_mesh = tf.expand_dims(xy_mesh, -1)
	xy_mesh = tf.reshape(xy_mesh, [x_size,y_size,2,1])
	# Frequency logspace of nyquist f for bands
	up_lim = tf.math.log(Fs/2)/tf.math.log(10.)
	low_lim = math.log(1)
	f_sin = tf.math.sin(tf.experimental.numpy.logspace(low_lim, up_lim, bands) * math.pi)
	f_cos = tf.math.cos(tf.experimental.numpy.logspace(low_lim, up_lim, bands) * math.pi)
	t = tf.concat([f_sin, f_cos], axis=0)
	t = tf.concat([t, [1.]], axis=0) # Size is now 2K+1
	# Get encoding/features
	encoding = xy_mesh * t
	encoding = tf.reshape(encoding, [1, x_size, y_size, (2 * bands + 1) * 2])
	encoding = tf.repeat(encoding, n, 0) # Repeat for all images (on first axis)
	img = tf.expand_dims(img, axis=-1) # resize image data so that it fits
	out = tf.concat([img, encoding], axis=-1) # Add image data
	out = tf.reshape(out, [n, x_size * y_size, -1]) # Linearise
	return out

# ##### Define Modules #####

INPUT_SHAPE			= (IMG_WIDTH, IMG_HEIGHT, 1)
LATENT_ARRAY_SIZE	= 512 # Same as paper
BYTE_ARRAY_SIZE		= IMG_HEIGHT * IMG_WIDTH
DATA_LENGTH			= 2 * (2 * BANDS + 1) + 1
QKV_DIM				= DATA_LENGTH
CD_DIM				= 256
EPSILON				= 1e-5
LEARNING_RATE		= 0.001
VALIDATION_SPLIT	= 0.2
EPOCHS				= 50
DROPOUT_RATE		= 0.2

TRANSFOMER_NUM		= 2
MODULES_NUM			= 2
OUT_SIZE			= 1 # binary as only left or right knee

def network_connection(hidden_layers):
	connection_model = tf.keras.models.Sequential()
	for i in hidden_layers[:-1]:
		connection_model.add(tf.keras.layers.Dense(i, activation='relu'))
	connection_model.add(tf.keras.layers.Dense(units = hidden_layers[-1]))
	connection_model.add(tf.keras.layers.Dropout(DROPOUT_RATE))
	return connection_model

def network_attention():
	# Network structure starting at latent array
	latent_layer = tf.keras.layers.Input(shape = [LATENT_ARRAY_SIZE, DATA_LENGTH])
	#latent_layer = tf.keras.layers.LayerNormalization(epsilon=EPSILON)(latent_layer) # Add a cheeky normalization layer
	query_layer  = tf.keras.layers.Dense(QKV_DIM)(latent_layer) # Query tensor (dense layer)

	# Network structure starting at byte array
	byte_layer  = tf.keras.layers.Input(shape = [BYTE_ARRAY_SIZE, DATA_LENGTH])
	#byte_layer  = tf.keras.layers.LayerNormalization(epsilon=EPSILON)(byte_layer) # Add a cheeky normalization layer
	key_layer   = tf.keras.layers.Dense(QKV_DIM)(byte_layer) # Key tensor (dense layer)
	value_layer = tf.keras.layers.Dense(QKV_DIM)(byte_layer) # Value tensor (dense layer)

	# Combine byte part into cross attention node thingy
	attention_layer = tf.keras.layers.Attention(use_scale=True, dropout=DROPOUT_RATE)([query_layer, key_layer, value_layer])
	attention_layer = tf.keras.layers.Dense(QKV_DIM)(attention_layer)
	attention_layer = tf.keras.layers.Dense(QKV_DIM)(attention_layer)
	attention_layer = tf.keras.layers.LayerNormalization()(attention_layer)

	# Combine latent array into cross attention node thingy
	attention_layer = tf.keras.layers.Add()([attention_layer, latent_layer]) # Add a sneaky connection straight from latent
	attention_layer = tf.keras.layers.LayerNormalization()(attention_layer)

	# Need to now add a connecting layer
	connector_layer = network_connection([CD_DIM, CD_DIM])
	attention_connect_layer = connector_layer(attention_layer)
	
	# Should probably also normalize
	return attention_connect_layer

def network_transformer():
	# Get latent_size and DATA_LENGTH
	latent_input_initial = tf.keras.layers.Input(shape = [LATENT_ARRAY_SIZE, DATA_LENGTH])
	latent_input = latent_input_initial
	# Create as many transformer modules as necessary
	for i in range(TRANSFOMER_NUM):
		transformer_layer = tf.keras.layers.LayerNormalization()(latent_input) # probs remove above normalization
		# Multihead attention layer
		transformer_layer = tf.keras.layers.MultiHeadAttention(num_heads = TRANSFOMER_NUM, key_dim = DATA_LENGTH)(transformer_layer,transformer_layer)
		# Add passthrough connection from input
		transformer_layer = tf.keras.layers.Add()([latent_input, transformer_layer])
		# Normalize for the fun of it
		transformer_layer = tf.keras.layers.LayerNormalization()(transformer_layer)
		# Get query
		x = tf.keras.layers.Dense(DATA_LENGTH, input_dim=DATA_LENGTH)(transformer_layer)
		x = tf.keras.layers.Dense(DATA_LENGTH, input_dim=DATA_LENGTH)(x)
		x = tf.keras.layers.Dropout(DROPOUT_RATE)(x)
		# Add passthrough connection from transformer_layer
		transformer_layer = tf.keras.layers.Add()([x, transformer_layer])
		latent_input = transformer_layer # sketchy but also works
	# Add global pooling layer (not really part of transformer, but I don't care)
	out = tf.keras.Model(inputs = latent_input_initial, outputs = transformer_layer)
	return out

# ##### Create Perceiver Module #####

# Perceiver class
class Perceiver(tf.keras.Model):
	def __init__(self):
		super(Perceiver, self).__init__()

	def build(self, input_shape):
		# Intialise input
		self.in_layer = self.add_weight(shape = (LATENT_ARRAY_SIZE, DATA_LENGTH), initializer = 'random_normal', trainable = True)
		#self.in_layer = tf.reshape(self.in_layer, (1,*self.in_layer.shape))
		# Add attention module
		#self.attention = network_attention()
		# Add transformer module
		#self.transformer = network_transformer()
		# Build
		super(Perceiver, self).build(input_shape)

	def call(self, inputs):
		# Attention input
		frequency_data = pos_encoding(xtrain, 4, 20)
		#attention_in = [self.in_layer, frequency_data]
		attention_in = self.in_layer
		#attention_in = {"latent_layer": tf.expand_dims(self.in_layer, axis=0),
		#				"byte_layer"  : inputs}
		# Add a bunch of attention/transformer layers
		#for i in range(MODULES_NUM):
		#latent = self.attention(attention_in)
		#	query = self.transformer(latent)
		#	attention_in[1] = query
		#for i in range(MODULES_NUM):
		#	latent_layer = self.attention(attention_in) # Latent array -> attention layer
		#	latent_layer = self.transformer(latent_layer)
		#	attention_in["latent_layer"] = latent_layer
		# Pooling
		#out = tf.keras.layers.GlobalAveragePooling1D(1, query)
		#out = tf.keras.layers.LayerNormalization()(out)
		final = tf.keras.layers.Dense(OUT_SIZE, activation='softmax')(attention_in)
		return final

# ##### Run Training/Evaluation #####

# Make the model using the perceiver class
perceiver = Perceiver()

# Compile the model
perceiver.compile(
	optimizer=tfa.optimizers.LAMB(learning_rate=LEARNING_RATE),
	#loss=tf.keras.losses.SparseCategoricalCrossentropy(),
	loss='categorical_crossentropy',
	metrics=tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy"))

print("xtrain shape:", xtrain.shape)
print("ytrain shape:", ytrain.shape)

# Non-constant learning rate
adjust_learning_rate = tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor = 0.1, patience = 1, restore_best_weights = False)

# Perform model fit
#model_history = perceiver.fit(x = xtrain, y = ytrain, batch_size = BATCH_SIZE, epochs = EPOCHS, validation_split = VALIDATION_SPLIT, callbacks = [adjust_learning_rate])
model_history = perceiver.fit(x = xtest, y = ytest)

_, accuracy, top_5_accuracy = perceiver.evaluate(xtest, ytest)

print("Accuracy:", accuracy)
print("Top 5 Accuracy:", top_5_accuracy)

# ##### Finish #####
print("Finished with no errors")
