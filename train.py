import argparse
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' # disable tensorflow debugging logs
import tensorflow as tf
from tensorflow.keras.applications import vgg16
from tensorflow.keras.mixed_precision import experimental as mixed_precision
import numpy as np
import time
from model import ImageTransformNet, LossNetwork
from utils import convert, style_loss, content_loss, gram_matrix
from hparams import hparams
AUTOTUNE = tf.data.experimental.AUTOTUNE
policy = mixed_precision.Policy('mixed_float16')
mixed_precision.set_policy(policy)


def create_ds(args):  
    train_list_ds = tf.data.Dataset.list_files(str(args.content_dir + '*.jpg'), shuffle=True)
    train_images_ds = train_list_ds.map(convert, num_parallel_calls=AUTOTUNE)  
    ds = train_images_ds.repeat().batch(hparams['batch_size']).prefetch(buffer_size=AUTOTUNE)
    return ds


def create_test_batch(args):# Paper original content images
    test_content_img = ['avril_cropped.jpg', 
                        'taj_mahal.jpg',
                        'chicago_cropped.jpg']
    test_content_batch = tf.concat(
        [convert(os.path.join(args.test_img, img))[tf.newaxis, :] for img in test_content_img], axis=0)
    return test_content_batch


def run_training(args): 
    it_network = ImageTransformNet(input_shape=hparams['input_size'])
    loss_network = LossNetwork()

    optimizer = tf.keras.optimizers.Adam(learning_rate=hparams['learning_rate'])
    optimizer = mixed_precision.LossScaleOptimizer(optimizer, loss_scale='dynamic')
    
    ckpt_dir = os.path.join(args.name, 'pretrained')
    ckpt = tf.train.Checkpoint(network=it_network,
                               optimizer=optimizer,        
                               step=tf.Variable(0))
    ckpt_manager = tf.train.CheckpointManager(ckpt, 
                                              directory=ckpt_dir, 
                                              max_to_keep=args.max_ckpt_to_keep)
                                              
    ckpt.restore(ckpt_manager.latest_checkpoint)
    if ckpt_manager.latest_checkpoint:
        print("Restored from {}".format(ckpt_manager.latest_checkpoint))
    else:
        print("Initializing from scratch.")

    log_dir = os.path.join(args.name, 'log_dir')
    writer = tf.summary.create_file_writer(log_dir)
    total_loss_avg = tf.keras.metrics.Mean()
    style_loss_avg = tf.keras.metrics.Mean()
    content_loss_avg = tf.keras.metrics.Mean()

    style_img = convert(args.style_img)
    target_feature_maps = loss_network(vgg16.preprocess_input(style_img[tf.newaxis, :]))
    target_gram_matrices = [gram_matrix(x) for x in target_feature_maps]
    num_style_layers = len(target_feature_maps)
    
    dataset = create_ds(args)
    test_content_batch = create_test_batch(args)

    def train_step(batch):
        with tf.GradientTape() as tape:
            output_batch = it_network(batch)
            # Feed target and output batch through loss_network
            target_batch_feature_maps = loss_network(vgg16.preprocess_input(batch))
            output_batch_feature_maps = loss_network(vgg16.preprocess_input(output_batch))
            
            c_loss = content_loss(target_batch_feature_maps[2],
                                  output_batch_feature_maps[2])     
            c_loss *= hparams['content_weight']

            # Get output gram_matrix
            output_gram_matrices = [gram_matrix(x) for x in output_batch_feature_maps]
            s_loss = style_loss(target_gram_matrices, 
                                output_gram_matrices)
            s_loss *= hparams['style_weight'] / num_style_layers

            total_loss = c_loss + s_loss
            scaled_loss = optimizer.get_scaled_loss(total_loss)

        scaled_gradients = tape.gradient(scaled_loss, it_network.trainable_variables)
        gradients = optimizer.get_unscaled_gradients(scaled_gradients)
        #gradients = tape.gradient(total_loss, it_network.trainable_variables)
        optimizer.apply_gradients(zip(gradients, it_network.trainable_variables))
        return total_loss, c_loss, s_loss
    
    total_start = time.time()
    for image in dataset:
        start = time.time()
        total_loss, c_loss, s_loss = train_step(image)
        total_loss_avg.update_state(total_loss)
        content_loss_avg.update_state(c_loss)
        style_loss_avg.update_state(s_loss)
        ckpt.step.assign_add(1)
        step_int = int(ckpt.step) # cast ckpt.step

        if (step_int) % args.checkpoint_interval == 0:
            ckpt_manager.save(step_int)
            prediction = it_network(test_content_batch)
            #prediction_norm = np.array(tf.clip_by_value(prediction, 0, 1)*255, dtype=np.uint8)
            prediction_norm = np.array(tf.clip_by_value(prediction, 0, 255), dtype=np.uint8)
    
            with writer.as_default():
                tf.summary.scalar('total loss', total_loss_avg.result(), step=step_int)
                tf.summary.scalar('content loss', content_loss_avg.result(), step=step_int)
                tf.summary.scalar('style loss', style_loss_avg.result(), step=step_int)
                images = np.reshape(prediction_norm, (-1, hparams['input_size'][0], 
                                                          hparams['input_size'][1], 3))
                tf.summary.image('generated image', images, step=step_int, max_outputs=3)
                
            print ('Step {} Loss: {:.4f}'.format(step_int, total_loss_avg.result())) 
            print ('Loss content: {:.4f}'.format(content_loss_avg.result()))
            print ('Loss style: {:.4f}'.format(style_loss_avg.result()))
            print ('Total time: {} sec'.format(time.time()-total_start))
            print ('Time taken for step {} is {} sec\n'.format(step_int, time.time()-start))
        

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--content_dir', default='./ms-coco/')
    parser.add_argument('--style_img', default='./images/style_img/mosaic.jpg')
    parser.add_argument('--name', default='model_4')
    parser.add_argument('--checkpoint_interval', type=int, default=50)
    parser.add_argument('--max_ckpt_to_keep', type=int, default=10)
    parser.add_argument('--test_img', default='./images/content_img/')
    
    args = parser.parse_args()

    run_training(args)

	
if __name__ == '__main__':
	main()