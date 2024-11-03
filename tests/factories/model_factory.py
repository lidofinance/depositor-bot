from typing import Any, Type, TypeVar

from eth_typing import ChecksumAddress, HexAddress, HexStr
from eth_utils import to_checksum_address
from faker import Faker
from hexbytes import HexBytes
from polyfactory.factories.base import BuildContext
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.field_meta import FieldMeta

T = TypeVar('T')


class Web3Factory(ModelFactory[T]):
    """
    Usage example:
        # Order required because of MRO
        class TableFactory(Web3FactoryModifier, ModelFactory[Table]):
    """

    __is_base_factory__ = True

    @classmethod
    def get_custom_types(cls) -> dict[Type, Any]:
        faker = Faker()

        return {
            ChecksumAddress: lambda: to_checksum_address(HexBytes(faker.binary(length=20)).hex()),
            HexAddress: lambda: HexBytes(faker.binary(length=20)).hex().lower(),
            HexStr: lambda: HexBytes(faker.binary(length=64)).hex(),
            HexBytes: lambda: HexBytes(faker.binary(length=64)),
        }

    @classmethod
    def _get_annotation(cls, field_name: str) -> Type | None:
        return cls.__model__.__annotations__.get(field_name)

    @classmethod
    def get_field_value(
        cls,
        field_meta: FieldMeta,
        field_build_parameters: Any | None = None,
        build_context: BuildContext | None = None,
    ) -> Any:
        annotation = cls._get_annotation(field_meta.name)

        if provider := cls.get_custom_types().get(annotation):
            return provider()

        return super().get_field_value(field_meta, field_build_parameters, build_context)

    @classmethod
    def batch_with(cls, **build_kwargs):
        """
        How to use:

            class B:
                num: int

            class A:
                id: int
                ref: b

            AFactory.batch_with(id=[2, 3], ref__num=[10, 20])

            # Is the same as next
            [
                AFactory.build(id=2, ref={'num': 10}),
                AFactory.build(id=3, ref=BFactory.build(num=20)),
            ]
        """
        expected_elements_num = len(list(build_kwargs.values())[0])
        assert all(len(param) == expected_elements_num for param in build_kwargs.values()), 'Invalid build params'

        kwargs_list = [dict(zip(build_kwargs.keys(), values)) for values in zip(*build_kwargs.values())]

        spread_data = []

        for param in kwargs_list:
            build_options = {}

            for key, value in param.items():
                path = build_options

                inserts = key.split('__')
                for i, insert in enumerate(inserts):
                    if i != len(inserts) - 1:
                        if insert not in path:
                            path[insert] = {}

                        path = path[insert]
                    else:
                        path[insert] = value

            spread_data.append(build_options)

        return [cls.build(**build_kwargs) for build_kwargs in spread_data]
