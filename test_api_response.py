import requests
import json

# Teszteljük az API-t
url = 'http://127.0.0.1:5000/api/tours?date=2025-10-24'

try:
    response = requests.get(url)
    if response.status_code == 200:
        tours = response.json()
        print(f"=== API VÁLASZ ===")
        print(f"Túrák száma: {len(tours)}")
        
        for tour in tours:
            print(f"\nTour #{tour['id']}: {tour['title']}")
            print(f"  Images: {len(tour.get('images', []))} db")
            
            for i, img in enumerate(tour.get('images', []), 1):
                print(f"    {i}. {img['filename']}")
                print(f"       URL: {img['url']}")
    else:
        print(f"API hiba: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"Hiba: {e}")