import array
import hashlib
from collections.abc import MutableSequence, Iterable
from dataclasses import dataclass, field
from typing import Callable, Optional, List
import itertools
import math
import pickle

@dataclass(kw_only=True)
class BloomFilter[T]:
    """
    A generic Bloom filter implementation for probabilistic membership testing.

    The Bloom filter efficiently tests whether an element is in a set, with a small probability of false positives.
    It supports customizable hash functions and multiple hashing passes.

    Attributes:
        bits (int): The number of bits in the Bloom filter.
        hash_func (Callable[[T], int]): A hash function that takes an input of type `T` and returns an integer hash. This will be split into N separate hash values for the filter.
        hash_digest_size (int): The size of the digest produced by the hash function, in bits.
        num_hashes (int): The number of hash passes to use (default is 5).
        bytes_per_hash (Optional[int]): The number of bytes allocated per hash function output (default is floor(self.hash_digest_size / self.num_hashes)).
        _bloom_filter (MutableSequence[int]): The internal representation of the Bloom filter, initialized after object creation.

    Example:
        ```python
        from hashlib import sha256

        def custom_hash(value: str) -> int:
            return int(sha256(value.encode()).hexdigest(), 16)

        bf = BloomFilter(bits=1024, hash_func=custom_hash, hash_digest_size=256)
        ```
    """
    bits : int
    hash_func : Callable[[T], int]
    hash_digest_size : int
    num_hashes : int = 5
    bytes_per_hash : Optional[int] = None
    _bloom_filter : MutableSequence[int] = field(init=False, repr=False)

    def __post_init__(self):
        self._argument_validation()
        self._bloom_filter = BitArray.zeroes(self.bits)
    
    @classmethod
    def from_iterable[T](cls, *, hash_func : Callable[[T], int], hash_digest_size : int, num_hashes : int, bytes_per_hash : int, iterable: Iterable):
        """
        Create a bloom filter from a pre-existing Iterable of bits. 
        Useful when deserializing from a pre-existing bloom filter source.
        """
        instance = object.__new__(cls)  # Create an instance without running __post_init__
        instance.bits = len(iterable)
        instance.hash_func = hash_func
        instance.hash_digest_size = hash_digest_size
        instance.num_hashes = num_hashes
        instance.bytes_per_hash = bytes_per_hash
        instance._bloom_filter = BitArray.from_iterable(iterable)
        return instance

    
    def estimate_false_positive_rate(self, n_items : int, *, pretty_print : bool = False) -> str:
        val = (1.0 - math.exp(- self.num_hashes * n_items / self.bits)) ** self.num_hashes
        if not pretty_print:
            return f"{val}"
        return f"False Positive Rate: {(val*100.0):.2f}%"
    
    def add(self, item : T):
        for hash_value in self._split_hash_values(item):
            self._bloom_filter[hash_value % len(self._bloom_filter)] = 0x1
    
    def serialize(self) -> bytes:
        """
        Serialize the bloom filter to be stored into a database or passed around elsewhere.\n
        This serializes only the _bloom_filter bit array variable, not the entire python object!
        """
        try:
            return self._bloom_filter.serialize()
        except:
            raise ValueError("Cannot serialize bloom filter as no serialize() function was found for the MutableSequence source!")
        
    def __contains__(self, item : T) -> bool:
        """
        If the item has ALL set bits within the bloom filter for each of the hash passes, then there is a *chance* it is in the dataset.
        \nIf it does not match even one of the hashed locations, then it cannot be in the set.
        """
        return all(self._bloom_filter[hash_value % len(self._bloom_filter)] for hash_value in self._split_hash_values(item))

    def _argument_validation(self):
        if self.num_hashes <= 0:
            raise ValueError("The number of hash functions must be greater than zero.")
        elif self.bytes_per_hash and self.hash_digest_size // self.num_hashes < self.bytes_per_hash:
            raise ValueError(f"Digest Size of {self.hash_digest_size} bytes is not large enough to support {self.num_hashes} hash functions at {self.bytes_per_hash} bytes per hash! You need at least {self.num_hashes * self.bytes_per_hash} bytes!")
        elif not self.bytes_per_hash:
            self.bytes_per_hash = self.hash_digest_size // self.num_hashes

    def _split_hash_values(self, item : T) -> List[int]:
        """
        Takes the given input and splits it using the hash function into num_hashes different hash values.
        """
        item_hash = self.hash_func(item)
        hash_bytes = item_hash.to_bytes(self.hash_digest_size)
        return [
            int.from_bytes(hash_bytes[i * self.bytes_per_hash:(i+1) * self.bytes_per_hash])
            for i in range(self.num_hashes)
        ]

@dataclass
class BitArray:
    """
    This is a wrapper class for a binary array because python would store 
    8 bytes per index rather than just 1 BIT.
    """
    data : array.array[int]
    size : int

    @staticmethod
    def _8_bools_to_int(bools) -> int:
        bin_str = ''.join('1' if b else '0' for b in reversed(bools))
        return int(bin_str, 2)

    @classmethod
    def _to_bytes(cls, iterable, iter_len_out: list):
        iterable = (bool(x) for x in iterable)
        iterable = itertools.batched(iterable, 8)
        iter_len = 0
        for x in iterable:
            iter_len += len(x)
            yield BitArray._8_bools_to_int(x)

        iter_len_out[0] = iter_len

    @classmethod
    def from_iterable(cls, iterable: Iterable):
        iter_len = [0]
        iterable = cls._to_bytes(iterable, iter_len_out=iter_len)
        data = array.array('B', iterable)
        size = iter_len[0]
        return cls(data=data, size=size)

    @classmethod
    def zeroes(cls, n : int):
        arr_size, remainder = divmod(n, 8)
        if remainder:
            arr_size += 1 # Round up
        data = array.array('B', (0 for _ in range(arr_size)))
        return cls(data=data, size=n)

    def _check_index(self, n : int):
        if not isinstance(n, int):
            raise TypeError("Expected Integer")
        if not 0 <= n <= self.size:
            raise IndexError(n)

    def __getitem__(self, n):
        self._check_index(n)
        arr_idx, bit_idx = divmod(n, 8)
        return (self.data[arr_idx] >> bit_idx) & 0xb1

    def __setitem__(self, n, bit):
        self._check_index(n)
        arr_idx, bit_idx = divmod(n, 8)
        data = self.data[arr_idx]
        data &= ~(1 << bit_idx) # clears bit
        data |= (bool(bit) * (1 << bit_idx)) # set
        self.data[arr_idx] = data
    
    def serialize(self) -> bytes:
        """
        Serializes the 
        """
        return pickle.dumps(self.data)

    def __repr__(self):
        return f"{self.__class__.__name__}({list(self)})"

    def __len__(self):
        return self.size

def sha256_hash(s : str) -> int:
    return int.from_bytes(hashlib.sha256(string=s.encode()).digest())
    

bloom_filter = BloomFilter[str](
    bits=40_000,
    hash_func=sha256_hash,
    hash_digest_size=256 // 8,
    num_hashes=5,
    bytes_per_hash=6
) # 5K bloom filter.
print(bloom_filter.estimate_false_positive_rate(4096, pretty_print=True))
bloom_filter.add("asjlkdjlasdljkas")
serialized = bloom_filter.serialize()
import sys
print(sys.getsizeof(serialized))
deserialized = pickle.loads(serialized)

bf2 = BloomFilter.from_iterable(
    hash_func=sha256_hash,
    hash_digest_size=256//8,
    num_hashes=5,
    bytes_per_hash=6,
    iterable=deserialized
)

print(bf2)