import argparse
import json
import sys

MULTI_VALUE_KEYS = ('cuisine', 'religion', 'vending', 'door')


def first_value(value):
    if not isinstance(value, str):
        return None
    for part in value.split(';'):
        part = part.strip()
        if part:
            return part
    return None


def normalize_properties(props, keys=MULTI_VALUE_KEYS):
    changed = 0
    for key in keys:
        value = props.get(key)
        if not isinstance(value, str):
            continue
        first = first_value(value)
        if first == value:
            continue
        if first is None:
            del props[key]
        else:
            props[key] = first
        changed += 1
    return changed


def normalize_collection(collection, keys=MULTI_VALUE_KEYS):
    changed = 0
    for feat in collection.get('features', []):
        props = feat.get('properties')
        if isinstance(props, dict):
            changed += normalize_properties(props, keys)
    return changed


def normalize_file(path, keys=MULTI_VALUE_KEYS):
    with open(path) as f:
        collection = json.load(f)
    changed = normalize_collection(collection, keys)
    if changed:
        with open(path, 'w') as out:
            json.dump(collection, out, ensure_ascii=False)
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='+')
    args = parser.parse_args(argv)
    for path in args.paths:
        changed = normalize_file(path)
        print(f"  {path} : {changed} valeurs multiples {'/'.join(MULTI_VALUE_KEYS)} réduites à la première")
    return 0


if __name__ == '__main__':
    sys.exit(main())
