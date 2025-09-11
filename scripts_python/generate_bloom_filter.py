"""Generate bloom filter data for character name validation."""

import os
import pickle

from bloom_filter import BloomFilter


def load_names_from_file(filepath: str) -> set:
    """Load names from a text file.

    Args:
        filepath: Path to the text file

    Returns:
        Set of lowercase names
    """
    names = set()
    with open(filepath, "r") as f:
        for line in f:
            name = line.strip().lower()
            if name:
                names.add(name)
    return names


def create_bloom_filter(names: set, false_positive_rate: float = 0.001) -> BloomFilter:
    """Create a bloom filter from a set of names.

    Args:
        names: Set of names to add to the filter
        false_positive_rate: Desired false positive rate

    Returns:
        Populated bloom filter
    """
    # Create bloom filter with appropriate size
    bloom = BloomFilter(max_elements=len(names) * 2, error_rate=false_positive_rate)

    # Add all names to the filter
    for name in names:
        bloom.add(name)

    return bloom


def main():
    """Generate bloom filter data for Lambda function."""
    # Get paths
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names_file = os.path.join(project_root, "data", "names.txt")
    obscenity_file = os.path.join(project_root, "data", "obscenity.txt")
    output_file = os.path.join(project_root, "lambda", "character_name_filter.pkl")

    # Load names from both files
    print("Loading copyrighted names...")
    copyrighted_names = load_names_from_file(names_file)
    print(f"Loaded {len(copyrighted_names)} copyrighted names")

    print("Loading obscenity list...")
    obscenities = load_names_from_file(obscenity_file)
    print(f"Loaded {len(obscenities)} obscenities")

    # Combine all restricted names
    all_restricted = copyrighted_names | obscenities
    print(f"Total restricted names: {len(all_restricted)}")

    # Create bloom filter
    print("Creating bloom filter...")
    bloom_filter = create_bloom_filter(all_restricted)

    # Save bloom filter to file
    print(f"Saving bloom filter to {output_file}...")
    with open(output_file, "wb") as f:
        pickle.dump(bloom_filter, f)

    # Calculate file size
    file_size = os.path.getsize(output_file)
    print(f"Bloom filter saved. File size: {file_size:,} bytes")

if __name__ == "__main__":
    main()
