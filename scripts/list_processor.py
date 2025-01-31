"""
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

def filter_single_word_entries(input_file: str, output_file: str) -> None:
    with open(input_file, "r", encoding="utf-8") as infile, open(output_file, "w", encoding="utf-8") as outfile:
        for line in infile:
            # Strip any leading/trailing whitespace and check if it's a single word
            word: str = line.strip()
            print(".", end="")
            if word and len(word.split()) == 1:  # Ensure it contains only one word
                outfile.write(word.lower() + "\n")


if __name__ == "__main__":
    input_list = "../data/en.txt"
    output_list = "../data/names.txt"
    filter_single_word_entries(input_list, output_list)
