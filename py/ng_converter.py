#!/bin/python

"""Converts old NgSkinTools data files to the new NgSkinTools2 format."""

import copy
import argparse
import json
import os


def convert(in_data):
    """Converts old NgSkinTools data format to the new NgSkinTools2 format.

    Args:
        in_data (dict): old NgSkinTools data format.

    Returns:
        dict: new NgSkinTools2 data format.
    """
    out_data = {
        'mesh': {
            'triangles': in_data['meshInfo']['triangles'],
            'vertPositions': in_data['meshInfo']['verts']
        },
        'influences': copy.deepcopy(list(in_data['influences'].values())),
    }

    # complete influences with missing keys
    for v in out_data['influences']:
        v.update({'labelText': '', 'labelSide': 0})

    # parse layers
    layers = []
    n_layers = len(in_data['layers'])
    for i, in_layer in enumerate(in_data['layers'][::-1]):
        out_layer = {
            'id': i + 1,
            'name': in_layer['name'],
            'enabled': in_layer['enabled'],
            'opacity': in_layer['opacity'],
            'paintTarget': 'mask',
            'parentId': n_layers - in_layer.get('parent', n_layers) or None,
            'children': [],
            'effects': {
                'mirrorMask': False,
                'mirrorWeights': False,
                'mirrorDq': False
            },
            'influences': {str(d['index']): d['weights']
                           for d in in_layer['influences']}
        }
        # setup layer mask and dualQuaternion weights, if any
        if in_layer['mask']:
            out_layer['mask'] = in_layer['mask']
        if in_layer['dqWeights']:
            out_layer['dq'] = in_layer['dqWeights']

        layers.append(out_layer)

    # setup layers hierarchy
    for layer in layers:
        par = layer['parentId']
        if par:
            layers[par - 1]['children'].append(layer['id'])
    # set each layer's index
    i = 0
    for layer in layers:
        if layer['parentId'] is None:
            layer['index'] = i
            i += 1
        for j, child in enumerate(layer['children']):
            layers[child - 1]['index'] = j

    # reorder layers so parents are declared before their children
    seen = {None}
    out_data['layers'] = []
    while layers:
        for layer in layers:
            if layer['parentId'] in seen:
                out_data['layers'].append(layer)
                seen.add(layer['id'])
                layers.remove(layer)
                break

    return out_data


def convert_from_path(source, destination=None):
    """ Convert source NgSkinTools1 file(s) to the new NgSkinTools2 format.

    Args:
        source (str): Path to the file or directory to convert.
        destination (str): Path to the destination file or directory.
    """
    if not os.path.exists(source):
        raise IOError("source doesn't exist: " + source)

    is_dir = os.path.isdir(source)
    if is_dir:
        if not destination:
            destination = source
        base = len(source) + 1
        fp = {os.path.join(x[0], y): os.path.join(destination, x[0][base:], y)
              for x in os.walk(source) for y in x[2] if y.endswith('.json')}
    else:
        fp = {source: destination or source}

    for k, v in sorted(fp.items()):
        print("converting {}\nto         {}\n".format(k, v))
        folder = os.path.dirname(v)
        if not os.path.exists(folder):
            os.makedirs(folder)
        json.dump(convert(json.load(open(k, 'r'))),
                  fp=open(v, 'w'), indent=2)


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('source', type=str)
    args.add_argument('destination', type=str, nargs='?')
    args = vars(args.parse_args())

    convert_from_path(args['source'], args['destination'])
