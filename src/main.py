import requests
import random
import os
import json
import imagehash
import argparse
from geopy.geocoders import Nominatim
from googletrans import Translator
from PIL import Image
from io import BytesIO
from collections import defaultdict
from tqdm import tqdm
from pathlib import Path


NUM_IMAGES = 20
DENSITY_RADIUS = {
    "high": 1000,  # Urban areas
    "medium": 5000,  # Rural areas
    "low": 10000,  # Remote areas
}


def main():
    api_key = get_api_key()

    json_bb_path = "bounding_boxes.json"
    try:
        with open(json_bb_path, "r") as json_file:
            country_bounding_boxes = json.load(json_file)
    except FileNotFoundError:
        print(f"Error: {json_bb_path} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    json_cords_path = "country_cords.json"
    try:
        with open(json_cords_path, "r") as json_file:
            country_to_cords = json.load(json_file)
    except FileNotFoundError:
        print(f"Error: {json_cords_path} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    country_to_cords = defaultdict(set, {k: set(tuple(v) for v in v_list) for k, v_list in country_to_cords.items()})

    for k, v in country_bounding_boxes.items():
        lat = random.uniform(v['min_lat'], v['max_lat'])
        lng = random.uniform(v['min_lng'], v['max_lng'])
        radius = DENSITY_RADIUS[v['density']]

        valid_coverage, data = check_street_view_coverage(lat, lng, radius, api_key)
        while not valid_coverage:
            lat = random.uniform(v['min_lat'], v['max_lat'])
            lng = random.uniform(v['min_lng'], v['max_lng'])
            valid_coverage, data = check_street_view_coverage(lat, lng, radius, api_key)

        pano_id = data['pano_id']
        lat = data['location']['lat']
        lng = data['location']['lng']
        geolocator = Nominatim(user_agent="my-app")
        try:
            location = geolocator.reverse(f"{lat},{lng}")
        except Exception as e:
            print(f"An error occurred: {e}")
            print(f'lat = {lat}, lng = {lng}')
            continue # continue with next country
            file_path = "country_cords.json"
            country_to_cords = {k: list(v) for k, v in country_to_cords.items()}
            with open(file_path, "w") as json_file:
                json.dump(country_to_cords, json_file, indent=4)
            return None
        try:
            country = location.address.split(", ")[-1]
        except Exception as e:
            print(f"An error occurred: {e} for {lat}, {lng}")
            continue # continue with next country
            file_path = "country_cords.json"
            country_to_cords = {k: list(v) for k, v in country_to_cords.items()}
            with open(file_path, "w") as json_file:
                json.dump(country_to_cords, json_file, indent=4)
            return None
        translator = Translator()
        country = translator.translate(country, src='auto', dest='en').text
        country = country.replace("/", "-")

        print(f'Searched for {k} ---> Country = {country}, lat = {lat}, lng = {lng}, pano_id = {pano_id}')
        country_to_cords[country].add((lat, lng, pano_id))

    file_path = "country_cords.json"
    country_to_cords = {k: list(v) for k, v in country_to_cords.items()}
    with open(file_path, "w") as json_file:
        json.dump(country_to_cords, json_file, indent=4)


def generate_images(api_key):
    json_cords_path = "country_cords.json"
    try:
        with open(json_cords_path, "r") as json_file:
            country_to_cords = json.load(json_file)
    except FileNotFoundError:
        print(f"Error: {json_cords_path} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    json_pano_path = "pano_ids.json"
    try:
        with open(json_pano_path, "r") as json_file:
            used_pano_ids = json.load(json_file)
    except FileNotFoundError:
        print(f"Error: {json_pano_path} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    country_to_cords = defaultdict(set, {k: set(tuple(v) for v in v_list) for k, v_list in country_to_cords.items()})
    used_pano_ids = set(used_pano_ids)

    for country, cords in tqdm(country_to_cords.items(), desc="Processing Countries", unit="country"):
        try:
            os.makedirs(f'data/{country}', exist_ok=True)
        except Exception as e:
            print(f"An error occurred: {e}")
            file_path = "pano_ids.json"
            used_pano_ids = list(used_pano_ids)
            with open(file_path, "w") as json_file:
                json.dump(used_pano_ids, json_file, indent=4)
            return None

        for lat, lng, pano_id in cords:
            if pano_id in used_pano_ids:
                continue
            used_pano_ids.add(pano_id)
            tiles = []
            for heading in range(0, 360, 90):
                row_tiles = []
                for pitch in [0]:  # Adjust pitch for 3 rows
                    tile = fetch_streetview_tile(api_key, lat, lng, heading, pitch)
                    row_tiles.append(tile)
                tiles.append(row_tiles)
            stitched_image = stitch_tiles(tiles)
            stitched_image.save(f"data/{country}/{pano_id}.jpg")

    file_path = "pano_ids.json"
    used_pano_ids = list(used_pano_ids)
    with open(file_path, "w") as json_file:
        json.dump(used_pano_ids, json_file, indent=4)


def get_api_key():
    file_path = "API.txt"
    try:
        with open(file_path, "r") as file:
            api_key = file.read().strip()  # Strip removes extra whitespace or newlines
    except FileNotFoundError:
        print(f"Error: {file_path} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    return api_key


def check_street_view_coverage(lat, lng, radius, api_key):
    """
    Check if Google Street View imagery exists for the given latitude and longitude.
    :param lat: Latitude.
    :param lng: Longitude.
    :return: True if imagery exists, False otherwise.
    """
    metadata_url = "https://maps.googleapis.com/maps/api/streetview/metadata"
    params = {
        "location": f"{lat},{lng}",
        'radius': radius,  # search radius in meters
        "key": api_key,
    }
    response = requests.get(metadata_url, params=params)
    data = response.json()

    if response.status_code == 200 and data["status"] == "OK":
        return True, data
    else:
        print(f"No Street View imagery for {lat}, {lng}: {data.get('status', 'Unknown error')}")
        return False, data


def stitch_tiles(tiles):
    rows = len(tiles[0])
    cols = len(tiles)
    tile_width, tile_height = tiles[0][0].size

    # Create a blank image canvas
    stitched_image = Image.new(
        "RGB", (cols * tile_width, rows * tile_height)
    )

    # Paste each tile into the correct position
    for col_idx, col in enumerate(tiles):
        for row_idx, tile in enumerate(col):
            stitched_image.paste(tile, (col_idx * tile_width, row_idx * tile_height))

    return stitched_image


def fetch_streetview_tile(api_key, lat, lng, heading=0, pitch=0, fov=90):
    base_url = "https://maps.googleapis.com/maps/api/streetview"
    params = {
        "size": "640x640",       # Image size
        "location": f"{lat},{lng}",
        "heading": heading,
        "pitch": pitch,
        "fov": fov,             # Field of View
        "key": api_key
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        return Image.open(BytesIO(response.content))
    else:
        print(f"Error fetching tile: {response.status_code} - {response.text}")
        return None


def update_used_pano_ids():
    num_images = sum([len(files) for _, _, files in os.walk("data")])
    json_pano_path = "pano_ids.json"
    try:
        with open(json_pano_path, "r") as json_file:
            used_pano_ids = json.load(json_file)
    except FileNotFoundError:
        print(f"Error: {json_pano_path} not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
    used_pano_ids = set(used_pano_ids)
    if len(used_pano_ids) == num_images:
        print('Images and Pano IDs Synced')
    else:
        print(f'Images and Pano IDs Not Synced: Images = {num_images}, Pano Ids = {len(used_pano_ids)}')
        root_path = Path("data")
        images = [file.name.replace(".jpg", "") for file in root_path.rglob("*") if file.is_file()]
        for img in images:
            if img not in used_pano_ids:
                used_pano_ids.add(img)
        if len(used_pano_ids) != num_images:
            print(f'Images and Pano IDs Not Synced: Images = {num_images}, Pano Ids = {len(used_pano_ids)}')
            assert(len(used_pano_ids) == num_images)
        file_path = "pano_ids.json"
        used_pano_ids = list(used_pano_ids)
        with open(file_path, "w") as json_file:
            json.dump(used_pano_ids, json_file, indent=4)

    json_cords_path = "country_cords.json"
    try:
        with open(json_cords_path, "r") as json_file:
            country_to_cords = json.load(json_file)
    except FileNotFoundError:
        print(f"Error: {json_cords_path} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    country_to_cords = defaultdict(set, {k: set(tuple(v) for v in v_list) for k, v_list in country_to_cords.items()})
    num_cords = sum([1 for country_cords in country_to_cords.values() for cord in country_cords])
    print(f"Cords = {num_cords}, Pano Ids = {len(used_pano_ids)}")


def get_center_crop(image, crop_fraction=0.5):
    """Crop the center of an image based on a given fraction."""
    width, height = image.size
    crop_width = int(width * crop_fraction)
    crop_height = int(height * crop_fraction)
    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    right = left + crop_width
    bottom = top + crop_height
    return image.crop((left, top, right, bottom))


def remove_duplicate_center_crops(template_path, folder_path, crop_fraction=0.5):
    """Remove images from folder whose center crops match the template."""
    # Load the template and compute its center crop hash
    template_image = Image.open(template_path)
    template_crop = get_center_crop(template_image, crop_fraction)
    template_hash = imagehash.average_hash(template_crop)

    json_pano_path = "pano_ids.json"
    try:
        with open(json_pano_path, "r") as json_file:
            used_pano_ids = json.load(json_file)
    except FileNotFoundError:
        print(f"Error: {json_pano_path} not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
    used_pano_ids = set(used_pano_ids)

    json_cords_path = "country_cords.json"
    try:
        with open(json_cords_path, "r") as json_file:
            country_to_cords = json.load(json_file)
    except FileNotFoundError:
        print(f"Error: {json_cords_path} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    # Iterate through images in the folder
    for root, _, files in os.walk(folder_path):
        print(f"Looking at {root}")
        for file in files:
            if file.endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
                image_path = os.path.join(root, file)
                try:
                    # Open the image and compute its center crop hash
                    image = Image.open(image_path)
                    image_crop = get_center_crop(image, crop_fraction)
                    image_hash = imagehash.average_hash(image_crop)

                    # Compare hashes
                    if image_hash == template_hash:
                        print(f"Removing duplicate: {image_path}")
                        pano_id = file.replace(".jpg", "")
                        used_pano_ids.remove(pano_id)
                        for country, coords in country_to_cords.items():
                            country_to_cords[country] = [coord for coord in coords if coord[2] != pano_id]
                        os.remove(image_path)

                except Exception as e:
                    print(f"Error processing {image_path}: {e}")
    file_path = "pano_ids.json"
    used_pano_ids = list(used_pano_ids)
    with open(file_path, "w") as json_file:
        json.dump(used_pano_ids, json_file, indent=4)

    file_path = "country_cords.json"
    country_to_cords = {k: list(v) for k, v in country_to_cords.items()}
    with open(file_path, "w") as json_file:
        json.dump(country_to_cords, json_file, indent=4)


def remove_error_images():
    template_image_path = "error.jpg"
    folder_to_check = "data"
    remove_duplicate_center_crops(template_image_path, folder_to_check)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cords", action="store_true", help="gets cords")
    parser.add_argument("--imgs", action="store_true", help="gets images")
    parser.add_argument("--sync", action="store_true", help="sync data")
    parser.add_argument("--err", action="store_true", help="check for errors")
    args = parser.parse_args()
    if args.cords:
        for _ in range(20):
            print("\n\n\n\n")
            main()
    if args.imgs:
        generate_images(get_api_key())
    if args.sync:
        update_used_pano_ids()
    if args.err:
        remove_error_images()