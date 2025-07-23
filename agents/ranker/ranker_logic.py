import asyncio
from typing import Dict, Any, List, Optional
import json

from common.db_client import DatabaseClient, get_db_client

class RankerAgent:
    """
    This agent is responsible for ranking posts based on engagement metrics.
    """
    def __init__(self):
        # Define weights for the scoring formula
        self.weights = {
            'views': 0.1,
            'likes': 0.3,
            'comments': 0.3,
            'reposts': 0.2,
            'shares': 0.1
        }

    async def _calculate_score(self, metrics: Dict[str, Optional[int]]) -> float:
        """Calculates a weighted score for a post."""
        score = 0.0
        for metric, weight in self.weights.items():
            value = metrics.get(metric)
            if value is not None:
                score += value * weight
        return round(score, 2)

    async def rank_posts(self, author_id: str, top_n: int = 5) -> Dict[str, Any]:
        """
        Ranks posts for a given author based on a weighted score.

        Args:
            author_id: The author's username (e.g., '@victor31429').
            top_n: The number of top posts to return.

        Returns:
            A dictionary containing the status and the ranked list of posts.
        """
        db_client = None
        try:
            db_client = await get_db_client()
            
            # Step 1: Get all post URLs for the author
            basic_posts = await db_client.get_posts_by_author(author_id.lstrip('@'))
            if not basic_posts:
                return {"status": "error", "message": f"No posts found for author: {author_id}"}
            
            post_urls = [p['url'] for p in basic_posts]

            # Step 2: Batch fetch posts with their metrics
            posts_with_metrics = await db_client.get_posts_with_metrics(post_urls)
            
            if not posts_with_metrics:
                 return {
                    "status": "error",
                    "message": f"Could not fetch metrics for posts of author: {author_id}"
                }

            scored_posts = []
            for post in posts_with_metrics:
                score = await self._calculate_score(post) # post dict contains all metrics
                
                metadata = post.get('metadata', {})
                if not isinstance(metadata, dict):
                    try:
                        metadata = json.loads(metadata) if metadata else {}
                    except (json.JSONDecodeError, TypeError):
                        metadata = {}
                        
                metadata['ranking_score'] = score
                await db_client.update_post_metadata(post['url'], metadata)

                scored_posts.append({
                    "url": post['url'],
                    "score": score
                })

            # Sort posts by score in descending order
            ranked_posts = sorted(scored_posts, key=lambda x: x['score'], reverse=True)
            
            # Add rank number
            final_ranked_list = []
            for i, p in enumerate(ranked_posts[:top_n]):
                p['rank'] = i + 1
                final_ranked_list.append(p)

            return {
                "status": "success",
                "ranked_posts": final_ranked_list,
                "message": f"Successfully ranked {len(final_ranked_list)} posts for {author_id}."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }
        # No finally block to disconnect, as get_db_client manages the pool.

# Example usage (for testing)
async def main():
    agent = RankerAgent()
    author = '@victor31429'
    result = await agent.rank_posts(author, top_n=5)
    import json
    print(json.dumps(result, indent=2))
    # Close the pool after the script is done
    db = await get_db_client()
    await db.close_pool()


if __name__ == '__main__':
    asyncio.run(main()) 