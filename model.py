import tensorflow as tf
from tensorflow.keras import layers
import tensorflow_addons as tfa
from hparams import hparams


class ConvReflect(tf.keras.layers.Layer):
    # 2D convolution layer with `padding` as "reflect".
    def __init__(self, filters, kernel_size, strides=(1, 1), 
                 kernel_initializer='glorot_uniform'):
        super(ConvReflect, self).__init__()
        self.size_pad = kernel_size // 2
        self.padding = tf.constant([[0, 0], 
                                    [self.size_pad, self.size_pad], 
                                    [self.size_pad, self.size_pad], 
                                    [0, 0]])
        self.conv2d = layers.Conv2D(filters, kernel_size, strides,
                                    kernel_initializer=kernel_initializer)

    def call(self, x):
        x = tf.pad(x, self.padding, "REFLECT") 
        x = self.conv2d(x)
        return x


def ImageTransformNet(input_shape=(256, 256, 3)):
    inputs = tf.keras.Input(shape=input_shape)

    x = ConvReflect(32, 9, kernel_initializer=hparams["initializer"])(inputs)
    x = tfa.layers.InstanceNormalization(axis=3, center=True, 
                                         scale=True,
                                         beta_initializer=hparams["initializer"],
                                         gamma_initializer=hparams["initializer"])(x)
    x = layers.Activation("relu")(x)
    
    x = ConvReflect(64, 3, strides=2, kernel_initializer=hparams["initializer"])(x)
    x = tfa.layers.InstanceNormalization(axis=3, center=True, 
                                         scale=True,
                                         beta_initializer=hparams["initializer"],
                                         gamma_initializer=hparams["initializer"])(x)
    x = layers.Activation("relu")(x)
    
    x = ConvReflect(64, 3, strides=2, kernel_initializer=hparams["initializer"])(x)
    x = tfa.layers.InstanceNormalization(axis=3, center=True, 
                                         scale=True,
                                         beta_initializer=hparams["initializer"],
                                         gamma_initializer=hparams["initializer"])(x)
    x = layers.Activation("relu")(x)

    for size in [hparams['residual_filters']]*hparams['residual_layers']:
        residual = x
        x = ConvReflect(size, 3, kernel_initializer=hparams["initializer"])(x)
        x = tfa.layers.InstanceNormalization(axis=3, center=True, 
                                             scale=True,
                                             beta_initializer=hparams["initializer"],
                                             gamma_initializer=hparams["initializer"])(x)

        x = layers.Activation("relu")(x)

        x = ConvReflect(size, 3, kernel_initializer=hparams["initializer"])(x)
        x = tfa.layers.InstanceNormalization(axis=3, center=True, 
                                             scale=True,
                                             beta_initializer=hparams["initializer"],
                                             gamma_initializer=hparams["initializer"])(x)
        x = layers.add([x, residual])  # Add back residual

    x = layers.UpSampling2D(2)(x)
    x = ConvReflect(64, 3, kernel_initializer=hparams["initializer"])(x)
    x = tfa.layers.InstanceNormalization(axis=3, center=True, 
                                         scale=True,
                                         beta_initializer=hparams["initializer"],
                                         gamma_initializer=hparams["initializer"])(x)
    x = layers.Activation("relu")(x)   

    x = layers.UpSampling2D(2)(x)
    x = ConvReflect(32, 3, kernel_initializer=hparams["initializer"])(x)
    x = tfa.layers.InstanceNormalization(axis=3, center=True, 
                                         scale=True,
                                         beta_initializer=hparams["initializer"],
                                         gamma_initializer=hparams["initializer"])(x)
    x = layers.Activation("relu")(x)
    
    x = ConvReflect(3, 9, kernel_initializer=hparams["initializer"])(x)
    outputs = layers.Activation('linear', dtype='float32')(x)

    return tf.keras.Model(inputs, outputs)


def LossNetwork():
    content_layers = ['block1_conv2',
                      'block2_conv2',
                      'block3_conv3', 
                      'block4_conv3'
    ]
    vgg = tf.keras.applications.vgg16.VGG16(include_top=False, weights='imagenet')
    vgg.trainable = False
    content_outputs = [vgg.get_layer(name).output for name in content_layers]
    model_outputs = content_outputs
    return tf.keras.models.Model(vgg.input, model_outputs)