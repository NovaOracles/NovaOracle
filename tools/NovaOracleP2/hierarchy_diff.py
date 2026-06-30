import argparse
import json
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


STATE_LABELS = {
    "text": "text",
    "content-desc": "content_desc",
    "checked": "checked",
    "selected": "selected",
}


DEFAULT_ATTRS_TO_CHECK = [
    "text",
    "content-desc",
    "checked",
    "selected",
]


IDENTITY_KEY_LEVELS = [
    "resource-id+class+bounds",
    "resource-id+class+index",
    "resource-id+class",
    "class+bounds",
    "class+index",
]


script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
default_datasets_root = project_root / "datasets"
default_output_dir = script_dir / "xml_diffs"


def clean_text_value(value):
    if value is None:
        return None

    cleaned = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Cf" and (unicodedata.category(char) != "Cc" or char in "\t\n\r")
    )
    return " ".join(cleaned.split())


def short_class(el):
    cls = el.get("class", "")
    return cls.split(".")[-1] if cls else "UnknownClass"


def build_parent_map(root):
    return {child: parent for parent in root.iter() for child in parent}


def child_index(element, parent_map):
    parent = parent_map.get(element)
    if parent is None:
        return -1

    try:
        return list(parent).index(element)
    except ValueError:
        return -1


def first_text_or_desc(element):
    for el in element.iter():
        name = clean_text_value(el.get("text")) or clean_text_value(el.get("content-desc"))
        if name:
            return name
    return None


def collect_texts(element, limit=None):
    texts = []
    for el in element.iter():
        name = clean_text_value(el.get("text"))
        if name and name not in texts:
            texts.append(name)
        if limit is not None and len(texts) >= limit:
            break
    return texts


def collect_content_descriptions(element, limit=None):
    descriptions = []
    for el in element.iter():
        name = clean_text_value(el.get("content-desc"))
        if name and name not in descriptions:
            descriptions.append(name)
        if limit is not None and len(descriptions) >= limit:
            break
    return descriptions


def compact_list(values, limit=8):
    return values[:limit]


def omitted_count(values, limit=8):
    return max(0, len(values) - limit)


def collect_actions(element, limit=8):
    actions = []
    action_classes = {"Button", "ImageButton", "CheckBox", "Switch", "CheckedTextView", "RadioButton"}

    for el in element.iter():
        if short_class(el) not in action_classes:
            continue

        name = clean_text_value(el.get("text")) or clean_text_value(el.get("content-desc"))
        if name and name not in actions:
            actions.append(name)
        if len(actions) >= limit:
            break

    return actions


def subtree_node_count(element):
    return sum(1 for _ in element.iter())


def control_summary(element):
    counts = defaultdict(int)
    interesting = {
        "TextView",
        "Button",
        "ImageButton",
        "EditText",
        "CheckBox",
        "Switch",
        "CheckedTextView",
        "RadioButton",
    }

    for el in element.iter():
        cls = short_class(el)
        if cls in interesting:
            counts[cls] += 1

    return dict(sorted(counts.items()))


def find_node_description(element, parent_map):
    name = first_text_or_desc(element)
    if name:
        return f'text_or_desc="{name}"'

    rid = element.get("resource-id")
    if rid:
        return f'resource_id="{rid}"'

    parent = parent_map.get(element)
    while parent is not None:
        for sibling in parent:
            if sibling is element:
                continue

            name = first_text_or_desc(sibling)
            if name:
                return f'near_text="{name}"'

        parent = parent_map.get(parent)

    bounds = element.get("bounds")
    if bounds:
        return f'class="{short_class(element)}", bounds="{bounds}"'

    return f'class="{short_class(element)}"'


def better_description(el1, el2, parent_map1, parent_map2):
    desc1 = find_node_description(el1, parent_map1)
    desc2 = find_node_description(el2, parent_map2)

    if not desc1.startswith('class="Unknown'):
        return desc1
    if not desc2.startswith('class="Unknown'):
        return desc2

    return desc1


def node_info(element, parent_map):
    parent = parent_map.get(element)
    sibling_index = ""
    if parent is not None:
        try:
            sibling_index = str(list(parent).index(element))
        except ValueError:
            sibling_index = ""

    return {
        "element": element,
        "index": element.get("index", sibling_index),
        "resource-id": element.get("resource-id", ""),
        "class": element.get("class", ""),
        "bounds": element.get("bounds", ""),
        "text": clean_text_value(element.get("text")) or "",
        "content-desc": clean_text_value(element.get("content-desc")) or "",
    }


def candidate_keys(info):
    rid = info["resource-id"]
    cls = info["class"]
    bounds = info["bounds"]
    index = info["index"]

    keys = []

    if rid and cls and bounds:
        keys.append(("resource-id+class+bounds", rid, cls, bounds))

    if rid and cls and index:
        keys.append(("resource-id+class+index", rid, cls, index))

    if rid and cls:
        keys.append(("resource-id+class", rid, cls))

    if cls and bounds:
        keys.append(("class+bounds", cls, bounds))

    if cls and index:
        keys.append(("class+index", cls, index))

    return keys


def parse_bounds(bounds):
    if not bounds:
        return None

    try:
        left_top, right_bottom = bounds.split("][")
        x1, y1 = left_top.lstrip("[").split(",")
        x2, y2 = right_bottom.rstrip("]").split(",")
        return tuple(map(int, (x1, y1, x2, y2)))
    except (ValueError, AttributeError):
        return None


def bounds_iou(bounds1, bounds2):
    rect1 = parse_bounds(bounds1)
    rect2 = parse_bounds(bounds2)
    if rect1 is None or rect2 is None:
        return 0.0

    x1, y1, x2, y2 = rect1
    a1, b1, a2, b2 = rect2

    inter_w = max(0, min(x2, a2) - max(x1, a1))
    inter_h = max(0, min(y2, b2) - max(y1, b1))
    inter_area = inter_w * inter_h

    area1 = max(0, x2 - x1) * max(0, y2 - y1)
    area2 = max(0, a2 - a1) * max(0, b2 - b1)
    union_area = area1 + area2 - inter_area

    if union_area == 0:
        return 0.0

    return inter_area / union_area


def bounds_similar(bounds1, bounds2):
    if bounds1 and bounds1 == bounds2:
        return True

    rect1 = parse_bounds(bounds1)
    rect2 = parse_bounds(bounds2)
    if rect1 is None or rect2 is None:
        return False

    if bounds_iou(bounds1, bounds2) >= 0.8:
        return True

    x1, y1, x2, y2 = rect1
    a1, b1, a2, b2 = rect2

    w1, h1 = max(1, x2 - x1), max(1, y2 - y1)
    w2, h2 = max(1, a2 - a1), max(1, b2 - b1)
    cx1, cy1 = (x1 + x2) / 2, (y1 + y2) / 2
    cx2, cy2 = (a1 + a2) / 2, (b1 + b2) / 2

    center_close = abs(cx1 - cx2) <= max(24, min(w1, w2) * 0.25) and abs(cy1 - cy2) <= max(
        24, min(h1, h2) * 0.5
    )
    size_close = min(w1, w2) / max(w1, w2) >= 0.6 and min(h1, h2) / max(h1, h2) >= 0.6

    return center_close and size_close


def rect_height(bounds):
    rect = parse_bounds(bounds)
    if rect is None:
        return None

    return max(0, rect[3] - rect[1])


def rect_vertical_overlap(bounds1, bounds2):
    rect1 = parse_bounds(bounds1)
    rect2 = parse_bounds(bounds2)
    if rect1 is None or rect2 is None:
        return 0.0

    _, y1, _, y2 = rect1
    _, b1, _, b2 = rect2
    overlap = max(0, min(y2, b2) - max(y1, b1))
    min_height = max(1, min(y2 - y1, b2 - b1))
    return overlap / min_height


def rect_center(bounds):
    rect = parse_bounds(bounds)
    if rect is None:
        return None

    x1, y1, x2, y2 = rect
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def contains_descendant(ancestor, descendant):
    return any(candidate is descendant for candidate in ancestor.iter())


def is_interactive_row_container(element, root):
    if element is root or element.tag == "hierarchy":
        return False

    if element.get("displayed") == "false":
        return False

    if element.get("clickable") != "true" and element.get("focusable") != "true":
        return False

    texts = collect_texts(element, limit=2)
    if not any(not is_weak_target_text(text) for text in texts):
        return False

    root_height = rect_height(root.get("bounds") or "")
    height = rect_height(element.get("bounds") or "")
    if root_height and height and height > root_height * 0.6:
        return False

    return True


def nearest_interactive_container(element, parent_map):
    root = element
    while parent_map.get(root) is not None:
        root = parent_map[root]

    parent = parent_map.get(element)
    while parent is not None:
        if is_interactive_row_container(parent, root) and contains_descendant(parent, element):
            return parent

        parent = parent_map.get(parent)

    return None


def text_candidates_in_container(container, control):
    control_bounds = control.get("bounds") or ""
    control_center = rect_center(control_bounds)
    candidates = []

    for order, candidate in enumerate(container.iter()):
        if candidate is control:
            continue

        name = clean_text_value(candidate.get("text")) or clean_text_value(candidate.get("content-desc"))
        if not name or is_weak_target_text(name):
            continue

        rid = (candidate.get("resource-id") or "").lower()
        if rid.endswith("/summary") or rid.endswith(":summary"):
            kind_score = 2
        elif rid.endswith("/title") or rid.endswith(":title"):
            kind_score = 0
        elif candidate.get("heading") == "true":
            kind_score = 4
        else:
            kind_score = 1

        candidate_bounds = candidate.get("bounds") or ""
        overlap = rect_vertical_overlap(candidate_bounds, control_bounds)
        center = rect_center(candidate_bounds)
        if center and control_center:
            x_penalty = 0 if center[0] <= control_center[0] else 1
            y_distance = abs(center[1] - control_center[1])
            x_distance = abs(center[0] - control_center[0])
        else:
            x_penalty = 0
            y_distance = 0
            x_distance = 0

        overlap_score = 0 if overlap > 0 else 1
        candidates.append((kind_score, overlap_score, x_penalty, y_distance, x_distance, order, name))

    return candidates


def label_from_container(container, control):
    candidates = text_candidates_in_container(container, control)
    if not candidates:
        return None

    candidates.sort(key=lambda item: item[:-1])
    return candidates[0][-1]


def semantic_target_for_control(element, parent_map):
    row = nearest_interactive_container(element, parent_map)
    if row is None:
        return None

    return label_from_container(row, element)


def is_state_text_change(element, attr, excluded_values):
    if attr != "text":
        return False

    if short_class(element) not in {"Switch", "CheckBox", "CheckedTextView", "RadioButton"}:
        return False

    values = {clean_text_value(value) for value in excluded_values if value is not None}
    return bool(values) and all(is_weak_target_text(value) for value in values)


def can_accept_key_match(level, info1, info2, child_count1, child_count2):
    if level == "class+index":
        return child_count1 == child_count2 and bounds_similar(info1["bounds"], info2["bounds"])

    return True


def match_node_lists(infos1, infos2):
    unmatched1 = set(range(len(infos1)))
    unmatched2 = set(range(len(infos2)))
    matches = {}

    for level in IDENTITY_KEY_LEVELS:
        index1 = defaultdict(list)
        index2 = defaultdict(list)

        for i in unmatched1:
            for key in candidate_keys(infos1[i]):
                if key[0] == level:
                    index1[key].append(i)

        for j in unmatched2:
            for key in candidate_keys(infos2[j]):
                if key[0] == level:
                    index2[key].append(j)

        common_keys = set(index1.keys()) & set(index2.keys())

        for key in common_keys:
            left = index1[key]
            right = index2[key]

            if len(left) == 1 and len(right) == 1:
                i = left[0]
                j = right[0]

                if i in unmatched1 and j in unmatched2 and can_accept_key_match(
                    level, infos1[i], infos2[j], len(infos1), len(infos2)
                ):
                    matches[i] = j
                    unmatched1.remove(i)
                    unmatched2.remove(j)

    return matches, unmatched1, unmatched2


def compare_attrs(el1, el2, attrs_to_check):
    changes = []

    for attr in attrs_to_check:
        old_value = clean_text_value(el1.get(attr))
        new_value = clean_text_value(el2.get(attr))

        if old_value != new_value:
            changes.append(
                {
                    "attribute": STATE_LABELS.get(attr, attr),
                    "from": old_value,
                    "to": new_value,
                }
            )

    return changes


def humanize_bool(value, attr):
    if value is None:
        return None

    if attr == "checked":
        return "checked" if value == "true" else "unchecked"

    if attr == "selected":
        return "selected" if value == "true" else "unselected"

    return value


def is_weak_target_text(value):
    if value is None:
        return True

    text = value.strip()
    if not text:
        return True

    normalized = text.lower()
    if normalized in {"on", "off", "true", "false", "checked", "unchecked", "selected", "unselected"}:
        return True

    if len(text) <= 2:
        return True

    return False


def first_meaningful(*values):
    for value in values:
        if value:
            return value
    return None


def infer_target(element, parent_map, attr=None, excluded_values=None):
    own_text = clean_text_value(element.get("text"))
    own_desc = clean_text_value(element.get("content-desc"))
    rid = element.get("resource-id") or ""
    resource_name = readable_resource_name(rid) if rid else None
    excluded = {value for value in (excluded_values or set()) if value}
    label = nearby_label(element, parent_map, exclude={own_text, own_desc, *excluded})
    cls = short_class(element)

    if attr in {"checked", "selected"}:
        own_name = first_meaningful(own_text, own_desc)
        if own_name and own_name not in excluded and not is_weak_target_text(own_name):
            return own_name
        control_target = semantic_target_for_control(element, parent_map)
        if control_target:
            return control_target
        return first_meaningful(label, resource_name, cls)

    if attr == "text":
        if is_state_text_change(element, attr, excluded):
            control_target = semantic_target_for_control(element, parent_map)
            if control_target:
                return control_target
        if "summary" in rid.lower() and label:
            return label
        if own_desc and own_desc not in excluded and not is_weak_target_text(own_desc):
            return own_desc
        if own_text and own_text not in excluded and not is_weak_target_text(own_text):
            return own_text
        return first_meaningful(label, resource_name, cls)

    if attr in {"content_desc", "content-desc"}:
        if own_text and own_text not in excluded and not is_weak_target_text(own_text):
            return own_text
        return first_meaningful(label, resource_name, cls)

    own_name = first_meaningful(own_text, own_desc)
    if own_name and own_name not in excluded and not is_weak_target_text(own_name):
        return own_name

    return first_meaningful(label, resource_name, cls)


def nearby_label(element, parent_map, exclude=None):
    excluded = {value for value in (exclude or set()) if value}
    parent = parent_map.get(element)
    while parent is not None:
        candidates = []
        siblings = list(parent)
        current_index = child_index(element, parent_map)

        for index, candidate in enumerate(siblings):
            if candidate is element:
                continue

            name = clean_text_value(candidate.get("text")) or clean_text_value(candidate.get("content-desc"))
            if name and name not in excluded and not is_weak_target_text(name):
                distance = abs(index - current_index) if current_index >= 0 else index
                candidates.append((distance, name))

        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]

        parent = parent_map.get(parent)

    return None


def readable_resource_name(resource_id):
    name = resource_id.split("/")[-1].split(":")[-1]
    return name.replace("_", " ").replace("-", " ")


def region_target(summary):
    if summary["primary_text"]:
        return summary["primary_text"]

    root = summary["root"]
    if root["description"]:
        return root["description"]

    return root["class"]


def node_brief(element, parent_map):
    return {
        "description": find_node_description(element, parent_map),
        "class": short_class(element),
        "resource_id": element.get("resource-id") or None,
        "bounds": element.get("bounds") or None,
    }


def summarize_subtree(element, parent_map):
    texts = collect_texts(element)
    content_descriptions = collect_content_descriptions(element)
    actions = collect_actions(element)
    text_limit = 8
    desc_limit = 8

    return {
        "root": node_brief(element, parent_map),
        "node_count": subtree_node_count(element),
        "primary_text": (texts or content_descriptions or [None])[0],
        "texts": compact_list(texts, text_limit),
        "text_count": len(texts),
        "omitted_text_count": omitted_count(texts, text_limit),
        "content_descriptions": compact_list(content_descriptions, desc_limit),
        "content_description_count": len(content_descriptions),
        "omitted_content_description_count": omitted_count(content_descriptions, desc_limit),
        "actions": actions,
        "control_counts": control_summary(element),
    }


def compact_region_change(change_type, subtree_summary):
    return {
        "change_type": change_type,
        "target": region_target(subtree_summary),
        "texts": subtree_summary["texts"],
        "text_count": subtree_summary["text_count"],
        "omitted_text_count": subtree_summary["omitted_text_count"],
        "content_descriptions": subtree_summary["content_descriptions"],
        "actions": subtree_summary["actions"],
        "node_count": subtree_summary["node_count"],
        "control_counts": subtree_summary["control_counts"],
    }


def has_semantic_content(region_change):
    return bool(
        region_change["texts"]
        or region_change["content_descriptions"]
        or region_change["actions"]
        or region_change["control_counts"]
    )


def diff_matched_pair(el1, el2, parent_map1, parent_map2, attrs_to_check, stats, records):
    if el1.tag != "hierarchy" and el2.tag != "hierarchy":
        changes = compare_attrs(el1, el2, attrs_to_check)

        if changes:
            for change in changes:
                stats["changed"] += 1
                records.append(
                    {
                        "target": infer_target(
                            el2,
                            parent_map2,
                            change["attribute"],
                            excluded_values={change["from"], change["to"]},
                        ),
                        "attribute": change["attribute"],
                        "from": humanize_bool(change["from"], change["attribute"]),
                        "to": humanize_bool(change["to"], change["attribute"]),
                    }
                )

    children1 = list(el1)
    children2 = list(el2)
    infos1 = [node_info(child, parent_map1) for child in children1]
    infos2 = [node_info(child, parent_map2) for child in children2]
    matches, unmatched1, unmatched2 = match_node_lists(infos1, infos2)

    stats["matched"] += len(matches)

    for i, j in sorted(matches.items()):
        diff_matched_pair(children1[i], children2[j], parent_map1, parent_map2, attrs_to_check, stats, records)


def diff_ui_tree(file1, file2, attrs_to_check=None, emit=True):
    if attrs_to_check is None:
        attrs_to_check = DEFAULT_ATTRS_TO_CHECK

    tree1 = ET.parse(file1)
    tree2 = ET.parse(file2)

    root1 = tree1.getroot()
    root2 = tree2.getroot()

    parent_map1 = build_parent_map(root1)
    parent_map2 = build_parent_map(root2)

    stats = {
        "matched_nodes": 0,
        "updates": 0,
    }
    internal_stats = {
        "matched": 0,
        "changed": 0,
    }
    records = []

    diff_matched_pair(root1, root2, parent_map1, parent_map2, attrs_to_check, internal_stats, records)

    stats["matched_nodes"] = internal_stats["matched"]
    stats["updates"] = internal_stats["changed"]

    result = {
        "updates": records,
    }

    if emit:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return result


def numeric_xml_key(path):
    try:
        return int(path.stem)
    except ValueError:
        return path.stem


def step_from_xml_name(path):
    return numeric_xml_key(Path(path))


def normalize_selector(value):
    return value.replace("\\", "/").strip().lower()


def hierarchy_roots(datasets_root):
    root = Path(datasets_root)
    return sorted(path for path in root.glob("*/hierarchy_files") if path.is_dir())


def example_metadata(example_dir, hierarchy_root):
    relative = example_dir.relative_to(hierarchy_root)
    parts = relative.parts

    return {
        "dataset": hierarchy_root.parent.name,
        "example": "/".join(parts),
        "app": parts[0] if parts else "",
        "case_id": parts[-1] if parts else example_dir.name,
    }


def selector_matches_example(selector, metadata):
    if not selector:
        return True

    normalized = normalize_selector(selector)
    dataset_example = normalize_selector(f"{metadata['dataset']}/{metadata['example']}")
    example = normalize_selector(metadata["example"])
    app = normalize_selector(metadata["app"])
    case_id = normalize_selector(metadata["case_id"])

    return normalized in {dataset_example, example, app, case_id} or dataset_example.endswith(f"/{normalized}")


def find_example_dirs(datasets_root, selector=None):
    matches = []

    for hierarchy_root in hierarchy_roots(datasets_root):
        for path in hierarchy_root.rglob("*"):
            if not path.is_dir():
                continue

            if not any(path.glob("*.xml")):
                continue

            metadata = example_metadata(path, hierarchy_root)
            if selector_matches_example(selector, metadata):
                matches.append((path, hierarchy_root, metadata))

    return sorted(matches, key=lambda item: (item[2]["dataset"], item[2]["example"]))


def diff_example_dir(example_dir, hierarchy_root):
    metadata = example_metadata(example_dir, hierarchy_root)
    xml_files = sorted(example_dir.glob("*.xml"), key=numeric_xml_key)
    diffs = []

    for old_xml, new_xml in zip(xml_files, xml_files[1:]):
        diff = diff_ui_tree(str(old_xml), str(new_xml), emit=False)
        diffs.append(
            {
                "from_step": step_from_xml_name(old_xml),
                "to_step": step_from_xml_name(new_xml),
                "updates": diff["updates"],
            }
        )

    return {
        "dataset": metadata["dataset"],
        "example": metadata["example"],
        "xml_count": len(xml_files),
        "diffs": diffs,
    }


def output_path_for_example(output_dir, metadata):
    return Path(output_dir) / f"{metadata['case_id']}.json"


def diff_dataset(datasets_root, output_dir=default_output_dir, selector=None):
    example_dirs = find_example_dirs(datasets_root, selector)
    if not example_dirs:
        raise FileNotFoundError(f"No hierarchy XML example found for selector: {selector!r}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []

    for example_dir, hierarchy_root, metadata in example_dirs:
        result = diff_example_dir(example_dir, hierarchy_root)
        output = output_path_for_example(output_dir, metadata)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs.append(
            {
                "dataset": metadata["dataset"],
                "example": metadata["example"],
                "output": str(output),
            }
        )

    return {"outputs": outputs}


def main():
    parser = argparse.ArgumentParser(description="Diff Android hierarchy XML files.")
    parser.add_argument(
        "--id",
        dest="selector",
        help="Optional example id, e.g. '321', 'WordPress/321', or 'RegDroid/WordPress/321'.",
    )
    args = parser.parse_args()

    diff_dataset(default_datasets_root, default_output_dir, args.selector)


if __name__ == "__main__":
    main()
