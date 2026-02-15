"""CacheQL - Server-side caching framework for GraphQL APIs.

A Python library for caching GraphQL responses with support for
Apollo Server-style @cacheControl directives, query-level and
field-level caching, multiple backends, and framework adapters
for Ariadne and Strawberry.

Example with Ariadne:
    from ariadne import make_executable_schema
    from cacheql import (
        CacheService,
        CacheConfig,
        InMemoryCacheBackend,
        DefaultKeyBuilder,
        JsonSerializer,
    )
    from cacheql.adapters.ariadne import CachingGraphQL

    # Schema with @cacheControl directives
    type_defs = '''
        directive @cacheControl(
            maxAge: Int
            scope: CacheControlScope
            inheritMaxAge: Boolean
        ) on FIELD_DEFINITION | OBJECT | INTERFACE | UNION

        enum CacheControlScope { PUBLIC PRIVATE }

        type Query {
            users: [User!]! @cacheControl(maxAge: 300)
            me: User @cacheControl(maxAge: 60, scope: PRIVATE)
        }

        type User @cacheControl(maxAge: 600) {
            id: ID!
            name: String!
        }
    '''

    schema = make_executable_schema(type_defs)

    # Create cache service
    config = CacheConfig(
        use_cache_control=True,
        default_max_age=0,  # No cache by default
    )
    cache_service = CacheService(
        backend=InMemoryCacheBackend(),
        key_builder=DefaultKeyBuilder(),
        serializer=JsonSerializer(),
        config=config,
    )

    # Create ASGI app with caching
    app = CachingGraphQL(schema, cache_service=cache_service)

Dynamic cache hints in resolvers:
    from cacheql.hints import set_cache_hint, private_cache

    @query.field("user")
    async def resolve_user(_, info, id: str):
        user = await get_user(id)
        set_cache_hint(info, max_age=300, scope="PRIVATE")
        return user
"""

from cacheql.core.entities import (
    CacheConfig,
    CacheControlConfig,
    CacheEntry,
    CacheHint,
    CacheKey,
    CacheScope,
    FieldCacheHint,
    ResponseCachePolicy,
)
from cacheql.core.interfaces import (
    ICacheBackend,
    IInvalidator,
    IKeyBuilder,
    ISerializer,
)
from cacheql.core.services import (
    CACHE_CONTROL_DIRECTIVE,
    CacheControlCalculator,
    CacheControlContext,
    CacheService,
    DirectiveParser,
    SchemaDirectives,
    create_cache_control_context,
    get_cache_control_directive_sdl,
)
from cacheql.decorators import cached, configure, invalidates
from cacheql.infrastructure import (
    DefaultKeyBuilder,
    InMemoryCacheBackend,
    JsonSerializer,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Core entities
    "CacheConfig",
    "CacheEntry",
    "CacheKey",
    # Cache control (Apollo-style)
    "CacheHint",
    "CacheScope",
    "FieldCacheHint",
    "ResponseCachePolicy",
    "CacheControlConfig",
    "CacheControlCalculator",
    "CacheControlContext",
    "create_cache_control_context",
    # Directive parsing
    "DirectiveParser",
    "SchemaDirectives",
    "CACHE_CONTROL_DIRECTIVE",
    "get_cache_control_directive_sdl",
    # Core interfaces
    "ICacheBackend",
    "IKeyBuilder",
    "ISerializer",
    "IInvalidator",
    # Core services
    "CacheService",
    # Infrastructure implementations
    "InMemoryCacheBackend",
    "DefaultKeyBuilder",
    "JsonSerializer",
    # Decorators
    "cached",
    "invalidates",
    "configure",
]
