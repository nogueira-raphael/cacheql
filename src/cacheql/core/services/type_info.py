"""Resolve GraphQL response field paths to their schema type names.

CacheControlCalculator needs to know which GraphQL type produced each
field in a response in order to apply type-level ``@cacheControl``
directives. Relying on ``__typename`` being present in the response is
unreliable: most clients only request it when they explicitly need it.

This module statically resolves that mapping from the query's AST and
the schema instead, mirroring what ``graphql-core`` does internally
during execution - no dependence on the actual response shape.
"""

from typing import Any

from graphql import GraphQLSchema, get_named_type, parse
from graphql.language import (
    DocumentNode,
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InlineFragmentNode,
    OperationDefinitionNode,
    OperationType,
    SelectionSetNode,
)
from graphql.type import GraphQLInterfaceType, GraphQLObjectType

# Types whose selection sets can be walked for field definitions.
_FieldedType = GraphQLObjectType | GraphQLInterfaceType

_OPERATION_TYPE_ATTR = {
    OperationType.QUERY: "query_type",
    OperationType.MUTATION: "mutation_type",
    OperationType.SUBSCRIPTION: "subscription_type",
}


def build_type_info(
    schema: GraphQLSchema,
    query: str,
    operation_name: str | None = None,
) -> dict[str, str]:
    """Map response field paths (dot-separated, alias-aware) to type names.

    Args:
        schema: The executable GraphQL schema.
        query: The raw GraphQL query/mutation document string.
        operation_name: The operation to resolve, if the document defines
            more than one.

    Returns:
        Mapping of ``"field.subfield"`` response paths to the GraphQL
        type name that resolves at that path. Empty if the query can't
        be parsed or no matching operation/root type is found.
    """
    try:
        document = parse(query)
    except Exception:
        return {}

    operation = _select_operation(document, operation_name)
    if operation is None:
        return {}

    root_type_attr = _OPERATION_TYPE_ATTR.get(operation.operation)
    root_type = getattr(schema, root_type_attr, None) if root_type_attr else None
    if root_type is None:
        return {}

    fragments = {
        d.name.value: d
        for d in document.definitions
        if isinstance(d, FragmentDefinitionNode)
    }

    type_info: dict[str, str] = {}
    _walk_selection_set(
        schema=schema,
        selection_set=operation.selection_set,
        parent_type=root_type,
        path=[],
        fragments=fragments,
        type_info=type_info,
        visited_fragments=frozenset(),
    )
    return type_info


def _select_operation(
    document: DocumentNode,
    operation_name: str | None,
) -> OperationDefinitionNode | None:
    operations = [
        d for d in document.definitions if isinstance(d, OperationDefinitionNode)
    ]
    if not operations:
        return None
    if operation_name is None:
        return operations[0]
    for op in operations:
        if op.name is not None and op.name.value == operation_name:
            return op
    return operations[0]


def _walk_selection_set(
    schema: GraphQLSchema,
    selection_set: SelectionSetNode | None,
    parent_type: Any,
    path: list[str],
    fragments: dict[str, FragmentDefinitionNode],
    type_info: dict[str, str],
    visited_fragments: frozenset[str],
) -> None:
    if selection_set is None:
        return

    fields = _fields_of(parent_type)

    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            field_name = selection.name.value
            if field_name.startswith("__"):
                continue

            field_def = fields.get(field_name)
            if field_def is None:
                continue

            response_key = selection.alias.value if selection.alias else field_name
            field_path = [*path, response_key]
            named_type = get_named_type(field_def.type)
            type_info[".".join(field_path)] = named_type.name

            if selection.selection_set is not None:
                _walk_selection_set(
                    schema=schema,
                    selection_set=selection.selection_set,
                    parent_type=named_type,
                    path=field_path,
                    fragments=fragments,
                    type_info=type_info,
                    visited_fragments=visited_fragments,
                )

        elif isinstance(selection, InlineFragmentNode):
            fragment_type = parent_type
            if selection.type_condition is not None:
                resolved = schema.get_type(selection.type_condition.name.value)
                if resolved is not None:
                    fragment_type = resolved
            _walk_selection_set(
                schema=schema,
                selection_set=selection.selection_set,
                parent_type=fragment_type,
                path=path,
                fragments=fragments,
                type_info=type_info,
                visited_fragments=visited_fragments,
            )

        elif isinstance(selection, FragmentSpreadNode):
            name = selection.name.value
            if name in visited_fragments:
                continue
            fragment_def = fragments.get(name)
            if fragment_def is None:
                continue
            fragment_type = (
                schema.get_type(fragment_def.type_condition.name.value)
                or parent_type
            )
            _walk_selection_set(
                schema=schema,
                selection_set=fragment_def.selection_set,
                parent_type=fragment_type,
                path=path,
                fragments=fragments,
                type_info=type_info,
                visited_fragments=visited_fragments | {name},
            )


def _fields_of(type_: Any) -> dict[str, Any]:
    if isinstance(type_, GraphQLObjectType | GraphQLInterfaceType):
        return dict(type_.fields)
    return {}
