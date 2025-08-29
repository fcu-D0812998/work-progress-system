import numpy as np
import csv
from PIL import Image, ImageDraw, ImageFont
import io

def calculate_angle_between_lines(p1, p2, p3, p4):
    v1 = np.array(p2) - np.array(p1)
    v2 = np.array(p4) - np.array(p3)
    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    angle = np.degrees(np.arccos(cos_angle))
    if angle > 90:
        angle = 180 - angle
    return angle

def calculate_intersection(p1, p2, p3, p4):
    a1, b1 = np.array(p1), np.array(p2)
    a2, b2 = np.array(p3), np.array(p4)
    d1, d2 = b1 - a1, b2 - a2
    A = np.column_stack([d1, -d2])
    b = a2 - a1
    try:
        t, _ = np.linalg.solve(A, b)
        intersection = a1 + t * d1
        return tuple(intersection)
    except np.linalg.LinAlgError:
        return None

def point_line_distance(pt, line):
    a, b = np.array(line[0]), np.array(line[1])
    pt = np.array(pt)
    return np.abs(np.cross(b - a, pt - a)) / np.linalg.norm(b - a)

def calculate_wetting_angles(csv_file):
    reader = csv.reader(csv_file)
    lines = list(reader)
    results = []
    for i in range(0, len(lines), 2):
        if i + 1 < len(lines):
            l1 = lines[i]
            l2 = lines[i + 1]
            p1 = (float(l1[1]), float(l1[2]))
            p2 = (float(l1[3]), float(l1[4]))
            p3 = (float(l2[1]), float(l2[2]))
            p4 = (float(l2[3]), float(l2[4]))
            image_name = l1[5]
            angle = calculate_angle_between_lines(p1, p2, p3, p4)
            intersection = calculate_intersection(p1, p2, p3, p4)
            results.append({
                'drop_id': i // 2 + 1,
                'image_name': image_name,
                'angle': angle,
                'line1': [p1, p2],
                'line2': [p3, p4],
                'intersection': intersection
            })
    return results

def draw_lines_on_image(image: Image.Image, results: list, output_io: io.BytesIO):
    img = image.convert('RGB')
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 80)
    except:
        font = ImageFont.load_default()

    for r in results:
        line1 = r['line1']
        line2 = r['line2']
        v1 = np.array(line1[1]) - np.array(line1[0])
        v2 = np.array(line2[1]) - np.array(line2[0])
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        arc_radius = min(norm_v1, norm_v2) * 0.2

        draw.line(line1, fill=(255, 0, 0), width=12)
        draw.line(line2, fill=(0, 0, 255), width=12)

        if r['intersection'] is not None:
            intersection = np.array(r['intersection'])
        else:
            intersection = np.mean([line1[0], line1[1], line2[0], line2[1]], axis=0)

        l1_far = line1[0] if np.linalg.norm(np.array(line1[0]) - intersection) > np.linalg.norm(np.array(line1[1]) - intersection) else line1[1]
        l2_far = line2[0] if np.linalg.norm(np.array(line2[0]) - intersection) > np.linalg.norm(np.array(line2[1]) - intersection) else line2[1]
        v1_dir = np.array(l1_far) - intersection
        v2_dir = np.array(l2_far) - intersection
        v1_dir /= np.linalg.norm(v1_dir)
        v2_dir /= np.linalg.norm(v2_dir)
        bisector = v1_dir + v2_dir
        if np.linalg.norm(bisector) != 0:
            bisector /= np.linalg.norm(bisector)
        else:
            bisector = v1_dir

        min_dist = 40
        scale = 4.0
        max_iter = 15
        for _ in range(max_iter):
            pos = intersection + bisector * (arc_radius * scale)
            d1 = point_line_distance(pos, line1)
            d2 = point_line_distance(pos, line2)
            if d1 > min_dist and d2 > min_dist:
                break
            scale += 0.3

        x, y = pos
        draw.text((x, y), f"{r['angle']:.1f}°", fill=(255, 0, 255), font=font)

    # 放大圖片
    scale_factor = 2
    new_size = (img.width * scale_factor, img.height * scale_factor)
    img = img.resize(new_size, Image.LANCZOS)

    # 存進 BytesIO（記憶體）
    img.save(output_io, format="JPEG")
