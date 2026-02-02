"""GraphQL schema definitions with @cacheControl directives."""

from cacheql.core.services.directive_parser import get_cache_control_directive_sdl

# Include the @cacheControl directive definition
CACHE_CONTROL_SDL = get_cache_control_directive_sdl()

TYPE_DEFS = CACHE_CONTROL_SDL + """
# =============================================================================
# Query Type
# =============================================================================

type Query {
    \"\"\"
    Get all users.
    Cached for 5 minutes (300 seconds), shared across all clients.
    \"\"\"
    users: [User!]! @cacheControl(maxAge: 300)

    \"\"\"
    Get a specific user by ID.
    Cached for 10 minutes (600 seconds).
    \"\"\"
    user(id: ID!): User @cacheControl(maxAge: 600)

    \"\"\"
    Get the currently authenticated user.
    Cached for 1 minute, PRIVATE (per-user cache).
    \"\"\"
    me: User @cacheControl(maxAge: 60, scope: PRIVATE)

    \"\"\"
    Get all posts.
    Cached for 5 minutes.
    \"\"\"
    posts: [Post!]! @cacheControl(maxAge: 300)

    \"\"\"
    Get a specific post by ID.
    Cached for 5 minutes.
    \"\"\"
    post(id: ID!): Post @cacheControl(maxAge: 300)

    \"\"\"
    Get database call statistics.
    Never cached (for debugging).
    \"\"\"
    dbStats: DbStats @cacheControl(maxAge: 0)
}

# =============================================================================
# Mutation Type
# =============================================================================

type Mutation {
    \"\"\"Update a user's information.\"\"\"
    updateUser(id: ID!, name: String, email: String): User

    \"\"\"Create a new post.\"\"\"
    createPost(title: String!, content: String!, authorId: ID!): Post

    \"\"\"Delete a post.\"\"\"
    deletePost(id: ID!): Boolean!

    \"\"\"Reset database call statistics.\"\"\"
    resetDbStats: Boolean!
}

# =============================================================================
# Object Types
# =============================================================================

\"\"\"
A user in the system.
Default cache of 10 minutes at the type level.
\"\"\"
type User @cacheControl(maxAge: 600) {
    id: ID!
    name: String!

    \"\"\"
    User's email address.
    Marked as PRIVATE - will make entire response private if included.
    \"\"\"
    email: String! @cacheControl(scope: PRIVATE)

    \"\"\"
    Secret note - never cached (maxAge: 0).
    Including this field disables caching for the entire response.
    \"\"\"
    secretNote: String @cacheControl(maxAge: 0)

    \"\"\"Whether the user's profile is public.\"\"\"
    isPublicProfile: Boolean!

    \"\"\"
    Posts written by this user.
    Inherits maxAge from parent field.
    \"\"\"
    posts: [Post!]! @cacheControl(inheritMaxAge: true)

    \"\"\"When the user was created.\"\"\"
    createdAt: String!
}

\"\"\"
A blog post.
Default cache of 5 minutes.
\"\"\"
type Post @cacheControl(maxAge: 300) {
    id: ID!
    title: String!
    content: String!

    \"\"\"
    The post's author.
    Inherits maxAge from parent (Post's 300s or query field's value).
    \"\"\"
    author: User! @cacheControl(inheritMaxAge: true)

    \"\"\"When the post was created.\"\"\"
    createdAt: String!
}

\"\"\"Database call statistics for debugging.\"\"\"
type DbStats {
    getUsersCalls: Int!
    getUserCalls: Int!
    getPostsCalls: Int!
    getPostCalls: Int!
    getUserPostsCalls: Int!
}
"""
