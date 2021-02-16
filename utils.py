from typing import List, TypeVar

import demoji

T = TypeVar("T")


def unique_list(lst: List[T]) -> List[T]:
    n = []
    for item in lst:
        if item not in n:
            n.append(item)
    return n


def split_into_chunks(l, n):
    return [l[i : i + n] for i in range(0, len(l), n)]


def get_name_from_author_obj(data):
    username = data["username"]
    first_name = data["first_name"]
    return username or first_name


def find_emojis_in_str(s: str):
    return demoji.findall_list(s, False)
