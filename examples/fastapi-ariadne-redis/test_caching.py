#!/usr/bin/env python3
"""Test script to verify caching is working correctly."""

import asyncio
import httpx

BASE_URL = "http://localhost:8000"
GRAPHQL_URL = f"{BASE_URL}/graphql"


async def graphql_query(client: httpx.AsyncClient, query: str, variables: dict = None):
    """Execute a GraphQL query."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    response = await client.post(GRAPHQL_URL, json=payload)
    return response


async def get_db_stats(client: httpx.AsyncClient) -> dict:
    """Get database call statistics."""
    query = """
    query {
        dbStats {
            getUsersCalls
            getUserCalls
            getPostsCalls
            getPostCalls
            getUserPostsCalls
        }
    }
    """
    response = await graphql_query(client, query)
    return response.json()["data"]["dbStats"]


async def reset_db_stats(client: httpx.AsyncClient):
    """Reset database call statistics."""
    mutation = """
    mutation {
        resetDbStats
    }
    """
    await graphql_query(client, mutation)


async def clear_cache(client: httpx.AsyncClient):
    """Clear the cache."""
    response = await client.post(f"{BASE_URL}/cache/clear")
    return response.json()


async def get_cache_stats(client: httpx.AsyncClient) -> dict:
    """Get cache statistics."""
    response = await client.get(f"{BASE_URL}/cache/stats")
    return response.json()


async def test_users_caching():
    """Test that users query is cached."""
    print("\n" + "=" * 60)
    print("TEST: Users Query Caching")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Clear cache and reset stats
        print("\n1. Clearing cache and resetting DB stats...")
        await clear_cache(client)
        await reset_db_stats(client)

        initial_stats = await get_db_stats(client)
        print(f"   Initial DB stats: getUsersCalls = {initial_stats['getUsersCalls']}")

        # First request - should hit the database
        print("\n2. Making first users request (should hit database)...")
        query = """
        query {
            users {
                id
                name
            }
        }
        """
        response = await graphql_query(client, query)
        cache_header = response.headers.get("X-Cache", "MISS")
        print(f"   Response X-Cache header: {cache_header}")
        print(f"   Response data: {response.json()['data']['users'][:2]}...")

        stats_after_first = await get_db_stats(client)
        print(f"   DB stats after first request: getUsersCalls = {stats_after_first['getUsersCalls']}")

        # Second request - should hit the cache
        print("\n3. Making second users request (should hit cache)...")
        response = await graphql_query(client, query)
        cache_header = response.headers.get("X-Cache", "MISS")
        print(f"   Response X-Cache header: {cache_header}")

        stats_after_second = await get_db_stats(client)
        print(f"   DB stats after second request: getUsersCalls = {stats_after_second['getUsersCalls']}")

        # Verify caching worked
        if stats_after_second['getUsersCalls'] == stats_after_first['getUsersCalls']:
            print("\n✅ SUCCESS: Cache is working! Second request did NOT hit the database.")
            return True
        else:
            print("\n❌ FAILURE: Cache is NOT working! Database was hit on second request.")
            return False


async def test_posts_caching():
    """Test that posts query is cached."""
    print("\n" + "=" * 60)
    print("TEST: Posts Query Caching")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Clear cache and reset stats
        print("\n1. Clearing cache and resetting DB stats...")
        await clear_cache(client)
        await reset_db_stats(client)

        # First request
        print("\n2. Making first posts request (should hit database)...")
        query = """
        query {
            posts {
                id
                title
            }
        }
        """
        response = await graphql_query(client, query)
        cache_header = response.headers.get("X-Cache", "MISS")
        print(f"   Response X-Cache header: {cache_header}")

        stats_after_first = await get_db_stats(client)
        print(f"   DB stats after first request: getPostsCalls = {stats_after_first['getPostsCalls']}")

        # Second request
        print("\n3. Making second posts request (should hit cache)...")
        response = await graphql_query(client, query)
        cache_header = response.headers.get("X-Cache", "MISS")
        print(f"   Response X-Cache header: {cache_header}")

        stats_after_second = await get_db_stats(client)
        print(f"   DB stats after second request: getPostsCalls = {stats_after_second['getPostsCalls']}")

        if stats_after_second['getPostsCalls'] == stats_after_first['getPostsCalls']:
            print("\n✅ SUCCESS: Cache is working for posts!")
            return True
        else:
            print("\n❌ FAILURE: Cache is NOT working for posts!")
            return False


async def test_user_by_id_caching():
    """Test that user by ID query is cached."""
    print("\n" + "=" * 60)
    print("TEST: User by ID Query Caching")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Clear cache and reset stats
        print("\n1. Clearing cache and resetting DB stats...")
        await clear_cache(client)
        await reset_db_stats(client)

        # First request
        print("\n2. Making first user(id: 1) request (should hit database)...")
        query = """
        query {
            user(id: "1") {
                id
                name
            }
        }
        """
        response = await graphql_query(client, query)
        cache_header = response.headers.get("X-Cache", "MISS")
        print(f"   Response X-Cache header: {cache_header}")

        stats_after_first = await get_db_stats(client)
        print(f"   DB stats after first request: getUserCalls = {stats_after_first['getUserCalls']}")

        # Second request
        print("\n3. Making second user(id: 1) request (should hit cache)...")
        response = await graphql_query(client, query)
        cache_header = response.headers.get("X-Cache", "MISS")
        print(f"   Response X-Cache header: {cache_header}")

        stats_after_second = await get_db_stats(client)
        print(f"   DB stats after second request: getUserCalls = {stats_after_second['getUserCalls']}")

        if stats_after_second['getUserCalls'] == stats_after_first['getUserCalls']:
            print("\n✅ SUCCESS: Cache is working for user by ID!")
            return True
        else:
            print("\n❌ FAILURE: Cache is NOT working for user by ID!")
            return False


async def test_cache_stats():
    """Test cache statistics endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Cache Statistics")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Clear cache
        await clear_cache(client)

        # Get initial cache stats
        print("\n1. Initial cache stats:")
        stats = await get_cache_stats(client)
        print(f"   Hits: {stats['stats']['hits']}, Misses: {stats['stats']['misses']}")

        # Make a query that will miss cache
        print("\n2. Making a query (will miss cache)...")
        query = "query { users { id name } }"
        await graphql_query(client, query)

        stats = await get_cache_stats(client)
        print(f"   After first query - Hits: {stats['stats']['hits']}, Misses: {stats['stats']['misses']}")

        # Make the same query (should hit cache)
        print("\n3. Making same query again (should hit cache)...")
        await graphql_query(client, query)

        stats = await get_cache_stats(client)
        print(f"   After second query - Hits: {stats['stats']['hits']}, Misses: {stats['stats']['misses']}")

        if stats['stats']['hits'] >= 1:
            print("\n✅ SUCCESS: Cache stats showing hits!")
            return True
        else:
            print("\n❌ FAILURE: No cache hits recorded!")
            return False


async def main():
    """Run all caching tests."""
    print("\n" + "=" * 60)
    print("CACHEQL CACHING VERIFICATION TESTS")
    print("=" * 60)
    print(f"\nTarget: {BASE_URL}")

    # Check health first
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            health = response.json()
            print(f"\nHealth check: {health['status']}")
            print(f"Redis: {health['redis']}")
            print(f"Cache enabled: {health['cache_enabled']}")
        except Exception as e:
            print(f"\n❌ ERROR: Could not connect to server: {e}")
            print("Make sure the server is running (docker-compose up)")
            return

    # Run tests
    results = []
    results.append(await test_users_caching())
    results.append(await test_posts_caching())
    results.append(await test_user_by_id_caching())
    results.append(await test_cache_stats())

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n✅ ALL TESTS PASSED - Caching is working correctly!")
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED - Caching needs investigation")


if __name__ == "__main__":
    asyncio.run(main())
