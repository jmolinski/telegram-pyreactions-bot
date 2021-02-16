from typing import Any, Dict, List, TypeVar, cast

import demoji

T = TypeVar("T")


def unique_list(lst: List[T]) -> List[T]:
    n = []
    for item in lst:
        if item not in n:
            n.append(item)
    return n


def split_into_chunks(lst: List[T], n: int) -> List[List[T]]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def get_name_from_author_obj(data: Dict[Any, Any]) -> str:
    username = data["username"]
    first_name = data["first_name"]
    return cast(str, username or first_name)


def find_emojis_in_str(s: str) -> List[str]:
    return cast(List[str], demoji.findall_list(s, desc=False))
