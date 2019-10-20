import hashlib
import io
import logging
import os

import PIL.Image
import tensorflow as tf

import sys
sys.path.append('..')

from object_detection.utils import dataset_util
from object_detection.utils import label_map_util

import pandas as pd

flags = tf.app.flags
flags.DEFINE_string('data_dir', '', 'Root directory to raw gtsdb dataset.')
flags.DEFINE_string('output_dir', '', 'Path to directory to output TFRecords.')
flags.DEFINE_string('label_map_path', 'gtsdb_label_map.pbtxt',
                    'Path to label map proto')
FLAGS = flags.FLAGS

def df_to_tf_example(data,
                       label_map_dict,
                       image_subdirectory):
  """Convert XML derived dict to tf.Example proto.

  Notice that this function normalizes the bounding box coordinates provided
  by the raw data.

  Args:
    data: dict holding PASCAL XML fields for a single image (obtained by
      running dataset_util.recursive_parse_xml_to_dict)
    label_map_dict: A map from string label names to integers ids.
    image_subdirectory: String specifying subdirectory within the
      Pascal dataset directory holding the actual image data.
    ignore_difficult_instances: Whether to skip difficult instances in the
      dataset  (default: False).

  Returns:
    example: The converted tf.Example.

  Raises:
    ValueError: if the image pointed to by data['filename'] is not a valid JPEG
  """
  img_path = os.path.join(image_subdirectory, data['filename'])
  with tf.gfile.GFile(img_path, 'rb') as fid:
    encoded_jpg = fid.read()
  encoded_jpg_io = io.BytesIO(encoded_jpg)
  image = PIL.Image.open(encoded_jpg_io)
  if image.format != 'JPEG':
    raise ValueError('Image format not JPEG')
  key = hashlib.sha256(encoded_jpg).hexdigest()

  width, height = image.size

  xmin = []
  ymin = []
  xmax = []
  ymax = []
  classes = []
  classes_text = []
  for obj in data['object']:

    xmin.append(float(obj['bndbox']['xmin']) / width)
    ymin.append(float(obj['bndbox']['ymin']) / height)
    xmax.append(float(obj['bndbox']['xmax']) / width)
    ymax.append(float(obj['bndbox']['ymax']) / height)
    class_name = label_map_dict[obj['class']]
    classes_text.append(class_name.encode('utf8'))
    classes.append(obj['class'])

  example = tf.train.Example(features=tf.train.Features(feature={
      'image/height': dataset_util.int64_feature(height),
      'image/width': dataset_util.int64_feature(width),
      'image/filename': dataset_util.bytes_feature(
          data['filename'].encode('utf8')),
      'image/source_id': dataset_util.bytes_feature(
          data['filename'].encode('utf8')),
      'image/key/sha256': dataset_util.bytes_feature(key.encode('utf8')),
      'image/encoded': dataset_util.bytes_feature(encoded_jpg),
      'image/format': dataset_util.bytes_feature('jpeg'.encode('utf8')),
      'image/object/bbox/xmin': dataset_util.float_list_feature(xmin),
      'image/object/bbox/xmax': dataset_util.float_list_feature(xmax),
      'image/object/bbox/ymin': dataset_util.float_list_feature(ymin),
      'image/object/bbox/ymax': dataset_util.float_list_feature(ymax),
      'image/object/class/text': dataset_util.bytes_list_feature(classes_text),
      'image/object/class/label': dataset_util.int64_list_feature(classes),
  }))
  return example


def create_tf_record(output_filename,
                     label_map_dict,
                     gt_path,
                     image_dir,
                     examples):
  """Creates a TFRecord file from examples.

  Args:
    output_filename: Path to where output file is saved.
    label_map_dict: The label map dictionary.
    gt_path: GT file path.
    image_dir: Directory where image files are stored.
    examples: Examples to parse and save to tf record.
  """
  writer = tf.python_io.TFRecordWriter(output_filename)

  # Read ground truth csv
  df = pd.read_csv(gt_path, delimiter=';', names=('file', 'xMin', 'yMin', 'xMax', 'yMax', 'classId'))
  df['file'] = df['file'].str.replace('ppm', 'jpg')

  for idx, example in enumerate(examples):
    if idx % 100 == 0:
      logging.info('On image %d of %d', idx, len(examples))

    data = {
        'filename': example,
        'object': []
    }
    objects = df[df['file'] == example]
    for _, obj in objects.iterrows():
        class_id = obj['classId'] + 1
        data['object'].append({
            'bndbox': {
                'xmin': obj['xMin'],
                'ymin': obj['yMin'],
                'xmax': obj['xMax'],
                'ymax': obj['yMax']
            },
            'class': class_id
        })

    tf_example = df_to_tf_example(data, label_map_dict, image_dir)
    writer.write(tf_example.SerializeToString())

  writer.close()

def main(_):
  data_dir = FLAGS.data_dir
  label_map_dict = label_map_util.get_label_map_dict(FLAGS.label_map_path)

  logging.info('Reading from GTSDB dataset.')
  image_dir = data_dir
  examples_gt_path = os.path.join(data_dir, 'gt.txt')
  examples_list = ['%05d.jpg' % x for x in range(900)]

  num_train = 600
  train_examples = examples_list[:num_train]
  val_examples = examples_list[num_train:]
  logging.info('%d training and %d validation examples.',
               len(train_examples), len(val_examples))

  train_output_path = os.path.join(FLAGS.output_dir, 'gtsdb_train.record')
  val_output_path = os.path.join(FLAGS.output_dir, 'gtsdb_val.record')
  create_tf_record(train_output_path, label_map_dict, examples_gt_path,
                   image_dir, train_examples)
  create_tf_record(val_output_path, label_map_dict, examples_gt_path,
                   image_dir, val_examples)

if __name__ == '__main__':
  tf.app.run()
