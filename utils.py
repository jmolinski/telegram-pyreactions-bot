import re

from typing import Any, Dict, List, Optional, TypeVar, cast

import demoji

from settings import get_settings

T = TypeVar("T")

CUSTOM_REACTION_PATTERN = re.compile("!react (.*)")


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


def get_reaction_representation(text: str, count: int, with_count: bool = False) -> str:
    if text == "-1":
        return f"-{count}"
    elif text == "+1":
        return f"+{count}"
    else:
        if with_count and count > 1:
            return f"{count} {text}"
        else:
            return text


def try_int(v: str, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(v)
    except:
        return default


def is_disallowed_reaction(r: str) -> bool:
    if r[0] in "-+":
        as_int = try_int(r[1:])
        if as_int is not None and as_int != 1:
            return True

    return r in get_settings().disallowed_reactions


def extract_custom_reaction(t: str) -> Optional[str]:
    t = t.strip()
    match = re.match(CUSTOM_REACTION_PATTERN, t)
    if match is None:
        return None

    reaction = match.group(1).strip()
    if not reaction or is_disallowed_reaction(reaction):
        return None

    return reaction


def _escape_markdown_v2(txt: str) -> str:
    return re.sub("(?=[~>#+-=|{}.!])", "\\\\", txt)
