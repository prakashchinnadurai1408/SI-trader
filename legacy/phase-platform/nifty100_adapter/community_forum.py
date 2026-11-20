"""Community Forum for SI-Trader Platform.

BRD Section 24: User community forum for strategy discussions,
experience sharing, and collaborative learning.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path


class PostStatus(Enum):
    """Status of a forum post."""
    ACTIVE = "active"
    MODERATED = "moderated"
    ARCHIVED = "archived"
    SPAM = "spam"


class PostType(Enum):
    """Type of forum post."""
    DISCUSSION = "discussion"
    QUESTION = "question"
    ANSWER = "answer"
    STRATEGY = "strategy"
    ANNOUNCEMENT = "announcement"
    SUCCESS_STORY = "success_story"


@dataclass
class ForumPost:
    """A single post in the community forum."""
    id: str
    author_id: str
    author_name: str
    post_type: PostType
    title: str
    content: str
    created_at: datetime
    updated_at: Optional[datetime]
    status: PostStatus = PostStatus.ACTIVE
    votes: int = 0
    replies: int = 0
    tags: List[str] = field(default_factory=list)
    viewed: int = 0


@dataclass
class ForumThread:
    """A thread (post + its replies) in the forum."""
    id: str
    title: str
    original_post: ForumPost
    replies: List[ForumPost] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    status: PostStatus = PostStatus.ACTIVE
    total_views: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


# Forum data storage
FORUM_DATA_DIR = Path(__file__).parent.parent / "user_data"
FORUM_DATA_DIR.mkdir(parents=True, exist_ok=True)
FORUM_INDEX_FILE = FORUM_DATA_DIR / "forum_index.json"


def _load_forum_index() -> Dict:
    """Load the forum index from disk."""
    if FORUM_INDEX_FILE.exists():
        try:
            with open(FORUM_INDEX_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"threads": [], "posts": {}}
    return {"threads": [], "posts": {}}


def _save_forum_index(index: Dict):
    """Save the forum index to disk."""
    with open(FORUM_INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=2)


def create_post(
    author_id: str,
    author_name: str,
    post_type: PostType,
    title: str,
    content: str,
    tags: Optional[List[str]] = None
) -> ForumPost:
    """Create a new forum post."""
    post_id = hashlib.sha256(
        f"{author_id}:{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]
    
    post = ForumPost(
        id=post_id,
        author_id=author_id,
        author_name=author_name,
        post_type=post_type,
        title=title,
        content=content,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        tags=tags or []
    )
    
    # Update index
    index = _load_forum_index()
    index["posts"][post_id] = {
        "id": post.id,
        "author_id": post.author_id,
        "author_name": post.author_name,
        "post_type": post.post_type.value,
        "title": post.title,
        "content": post.content,
        "created_at": post.created_at.isoformat(),
        "status": post.status.value,
        "votes": post.votes,
        "replies": post.replies,
        "tags": post.tags
    }
    
    # Add thread if this is a new topic
    if not any(t["id"] == post_id for t in index["threads"]):
        index["threads"].append({
            "id": post_id,
            "title": post.title,
            "original_post_id": post.id,
            "tags": post.tags,
            "status": post.status.value,
            "total_views": 0
        })
    
    _save_forum_index(index)
    return post


def create_reply(
    thread_id: str,
    author_id: str,
    author_name: str,
    content: str
) -> ForumPost:
    """Create a reply to an existing thread."""
    index = _load_forum_index()
    
    # Find the thread
    thread = None
    for t in index["threads"]:
        if t["id"] == thread_id:
            thread = t
            break
    
    if thread is None:
        raise ValueError(f"Thread {thread_id} not found")
    
    # Create the reply post
    reply_id = hashlib.sha256(
        f"{author_id}:{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]
    
    # Increment reply count on the thread
    thread["last_activity"] = datetime.now()
    
    reply = ForumPost(
        id=reply_id,
        author_id=author_id,
        author_name=author_name,
        post_type=PostType.REPLY,
        title="",
        content=content,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        tags=thread.get("tags", [])
    )
    
    # Add reply to thread
    thread["replies"].append({
        "id": reply.id,
        "author_id": reply.author_id,
        "author_name": reply.author_name,
        "post_type": "reply",
        "title": "",
        "content": reply.content,
        "created_at": reply.created_at.isoformat(),
        "status": PostStatus.ACTIVE.value,
        "votes": 0
    })
    thread["replies_count"] = len(thread.get("replies", []))
    
    _save_forum_index(index)
    return reply


def get_all_posts() -> List[ForumPost]:
    """Get all posts in the forum."""
    index = _load_forum_index()
    posts = []
    for post_id, post_data in index["posts"].items():
        if post_data["post_type"] != "reply":
            posts.append(ForumPost(
                id=post_id,
                author_id=post_data["author_id"],
                author_name=post_data["author_name"],
                post_type=PostType(post_data["post_type"]),
                title=post_data["title"],
                content=post_data["content"],
                created_at=datetime.fromisoformat(post_data["created_at"]),
                updated_at=datetime.fromisoformat(post_data["updated_at"]) if post_data.get("updated_at") else None,
                status=PostStatus(post_data["status"]),
                votes=post_data.get("votes", 0),
                replies=0,
                tags=post_data.get("tags", [])
            ))
    return posts


def get_thread(thread_id: str) -> Optional[ForumThread]:
    """Get a complete thread (original post + replies)."""
    index = _load_forum_index()
    
    # Find the thread
    thread_info = None
    for t in index["threads"]:
        if t["id"] == thread_id:
            thread_info = t
            break
    
    if thread_info is None:
        return None
    
    # Get the original post
    original_post = None
    for post_id, post_data in index["posts"].items():
        if post_id == thread_info["original_post_id"] and post_data["post_type"] != "reply":
            original_post = ForumPost(
                id=post_id,
                author_id=post_data["author_id"],
                author_name=post_data["author_name"],
                post_type=PostType(post_data["post_type"]),
                title=post_data["title"],
                content=post_data["content"],
                created_at=datetime.fromisoformat(post_data["created_at"]),
                updated_at=datetime.fromisoformat(post_data["updated_at"]) if post_data.get("updated_at") else None,
                status=PostStatus(post_data["status"]),
                votes=post_data.get("votes", 0),
                replies=0,
                tags=post_data.get("tags", [])
            )
            break
    
    if original_post is None:
        return None
    
    # Get replies
    replies = []
    for reply_data in thread_info.get("replies", []):
        replies.append(ForumPost(
            id=reply_data["id"],
            author_id=reply_data["author_id"],
            author_name=reply_data["author_name"],
            post_type=PostType.REPLY,
            title="",
            content=reply_data["content"],
            created_at=datetime.fromisoformat(reply_data["created_at"]),
            updated_at=datetime.fromisoformat(reply_data.get("updated_at", reply_data["created_at"])),
            status=PostStatus(reply_data["status"]),
            votes=reply_data.get("votes", 0),
            replies=0,
            tags=reply_data.get("tags", [])
        ))
    
    return ForumThread(
        id=thread_info["id"],
        title=thread_info["title"],
        original_post=original_post,
        replies=replies,
        tags=thread_info.get("tags", []),
        status=PostStatus(thread_info["status"]),
        total_views=thread_info.get("total_views", 0),
        created_at=datetime.fromisoformat(thread_info["created_at"]) if isinstance(thread_info["created_at"], str) else thread_info["created_at"],
        last_activity=datetime.fromisoformat(thread_info["last_activity"]) if isinstance(thread_info["last_activity"], str) else thread_info["last_activity"]
    )


def vote_post(post_id: str, vote_value: int) -> bool:
    """Upvote (1) or downvote (-1) a post."""
    index = _load_forum_index()
    
    if post_id not in index["posts"]:
        return False
    
    index["posts"][post_id]["votes"] = index["posts"][post_id].get("votes", 0) + vote_value
    # Ensure votes don't go negative
    index["posts"][post_id]["votes"] = max(index["posts"][post_id]["votes"], 0)
    
    _save_forum_index(index)
    return True


def get_forum_stats() -> Dict:
    """Get forum statistics."""
    index = _load_forum_index()
    posts = index["posts"]
    threads = index["threads"]
    
    total_posts = len([p for p in posts.values() if p["post_type"] != "reply"])
    total_threads = len(threads)
    total_replies = sum(len(t.get("replies", [])) for t in threads)
    total_views = sum(t.get("total_views", 0) for t in threads)
    
    # Most viewed thread
    most_viewed = max(threads, key=lambda t: t.get("total_views", 0)) if threads else None
    
    return {
        "total_threads": total_threads,
        "total_posts": total_posts,
        "total_replies": total_replies,
        "total_views": total_views,
        "most_viewed_thread": most_viewed["title"] if most_viewed else None,
        "active_threads": len([t for t in threads if t["status"] == "active"])
    }


# Initialize forum on import
def init_forum():
    """Initialize the forum data structure."""
    _load_forum_index()  # Ensure index file exists


# Export for web app integration
__all__ = [
    'PostStatus', 'PostType', 'ForumPost', 'ForumThread',
    'create_post', 'create_reply', 'get_all_posts', 'get_thread',
    'vote_post', 'get_forum_stats', 'init_forum'
]