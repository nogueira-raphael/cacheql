# cacheql Example: FastAPI + Ariadne + Redis

Este exemplo demonstra como usar o **cacheql** com FastAPI, Ariadne GraphQL e Redis como backend de cache.

## Features Demonstradas

- **@cacheControl directives** no schema GraphQL
- **Cache hints dinâmicos** nos resolvers
- **Redis** como backend de cache distribuído
- **Invalidação de cache** em mutations
- **HTTP Cache-Control headers** automáticos

## Requisitos

- Docker e Docker Compose

## Executando

### 1. Subir os containers

```bash
docker-compose up --build
```

A aplicação estará disponível em:
- **GraphQL Playground**: http://localhost:8000/graphql
- **Redis Commander** (UI): http://localhost:8081

### 2. Testar as queries

Abra o GraphQL Playground em http://localhost:8000/graphql e execute:

#### Query com cache (5 minutos)

```graphql
query {
  users {
    id
    name
    email
  }
}
```

Observe nos headers de resposta: `Cache-Control: max-age=300, public`

#### Query com cache privado (1 minuto)

```graphql
query {
  me {
    id
    name
    email
    secretNote
  }
}
```

Observe: `Cache-Control: max-age=60, private`

#### Query de um usuário específico

```graphql
query {
  user(id: "1") {
    id
    name
    posts {
      id
      title
      content
    }
  }
}
```

#### Mutation (invalida cache)

```graphql
mutation {
  updateUser(id: "1", name: "Alice Updated") {
    id
    name
  }
}
```

Esta mutation invalida o cache de usuários automaticamente.

### 3. Verificar o Redis

Acesse o Redis Commander em http://localhost:8081 para visualizar as chaves de cache.

Ou via CLI:

```bash
docker-compose exec redis redis-cli KEYS "*"
```

## Arquitetura do Exemplo

```
app/
├── main.py          # FastAPI app com Ariadne
├── schema.py        # Schema GraphQL com @cacheControl
├── resolvers.py     # Resolvers com cache hints
└── database.py      # Banco de dados fake (in-memory)
```

## Schema GraphQL

```graphql
directive @cacheControl(
  maxAge: Int
  scope: CacheControlScope
  inheritMaxAge: Boolean
) on FIELD_DEFINITION | OBJECT | INTERFACE | UNION

enum CacheControlScope {
  PUBLIC
  PRIVATE
}

type Query {
  # Cache público por 5 minutos
  users: [User!]! @cacheControl(maxAge: 300)

  # Cache público por 10 minutos
  user(id: ID!): User @cacheControl(maxAge: 600)

  # Cache privado por 1 minuto (dados do usuário atual)
  me: User @cacheControl(maxAge: 60, scope: PRIVATE)

  # Cache público por 5 minutos
  posts: [Post!]! @cacheControl(maxAge: 300)
}

type User @cacheControl(maxAge: 600) {
  id: ID!
  name: String!
  email: String! @cacheControl(scope: PRIVATE)
  secretNote: String @cacheControl(maxAge: 0)  # Nunca cachear
  posts: [Post!]! @cacheControl(inheritMaxAge: true)
}

type Post @cacheControl(maxAge: 300) {
  id: ID!
  title: String!
  content: String!
  author: User! @cacheControl(inheritMaxAge: true)
}
```

## Configuração do Cache

```python
from cacheql import CacheService, CacheConfig
from cacheql_redis import RedisCacheBackend

config = CacheConfig(
    enabled=True,
    use_cache_control=True,      # Usar @cacheControl directives
    default_max_age=0,           # Conservador: não cachear por padrão
    calculate_http_headers=True, # Gerar headers Cache-Control
    key_prefix="example",
)

backend = RedisCacheBackend(
    redis_url="redis://redis:6379",
    key_prefix="cacheql",
)

cache_service = CacheService(
    backend=backend,
    key_builder=DefaultKeyBuilder(),
    serializer=JsonSerializer(),
    config=config,
)
```

## Cache Hints Dinâmicos

```python
from cacheql.hints import set_cache_hint, private_cache, no_cache

@query.field("user")
async def resolve_user(_, info, id: str):
    user = await get_user(id)

    # Cache dinâmico baseado nos dados
    if user.get("is_public_profile"):
        set_cache_hint(info, max_age=3600, scope="PUBLIC")
    else:
        set_cache_hint(info, max_age=60, scope="PRIVATE")

    return user
```

## Parando os containers

```bash
docker-compose down
```

Para remover também os volumes (dados do Redis):

```bash
docker-compose down -v
```
