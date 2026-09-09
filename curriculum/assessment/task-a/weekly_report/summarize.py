"""把原始消息汇总成周报需要的统计量。"""
from collections import Counter


def count_by_author(messages):
    """每个人发了多少条消息。"""
    return Counter(m["sender"] for m in messages)


def count_words(messages):
    """每个人一共写了多少字（粗略按空白切分）。"""
    out = Counter()
    for m in messages:
        out[m["sender"]] += len(m["text"].split())
    return out


def top_contributors(counts, n=3):
    """按数量取前 n 名。"""
    ranked = sorted(counts.items(), key=lambda kv: kv[1])
    return [name for name, _ in ranked[:n]]


def collect_topics(messages):
    """抽出被 # 标记的话题。"""
    topics = Counter()
    for m in messages:
        for token in m["text"].split():
            if token.startswith("#") and len(token) > 1:
                topics[token[1:]] += 1
    return topics
