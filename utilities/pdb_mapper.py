#!/usr/bin/env python3
"""
PDB to EXE Mapper - Comprehensive Tool
Maps PDB symbols to EXE addresses with support for both debug and release builds.
"""

import struct
import os
import time


class PEFile:
    """Parser for PE (Portable Executable) file format."""

    def __init__(self, filepath):
        """Initialize the PE file parser."""
        self.filepath = filepath
        self.file_data = None
        self.image_base = 0
        self.entry_point = 0
        self.sections = []
        self.section_map = {}  # Maps PDB section number to PE section

    def read_file(self):
        """Read the PE file."""
        with open(self.filepath, 'rb') as f:
            self.file_data = f.read()
        return self.file_data

    def parse(self):
        """Parse the PE file header and section table."""
        # Read DOS header
        e_lfanew = struct.unpack('<I', self.file_data[60:64])[0]

        # Read PE signature
        pe_sig = self.file_data[e_lfanew:e_lfanew + 4]
        if pe_sig != b'PE\x00\x00':
            raise ValueError("Invalid PE signature")

        # Read file header
        machine = struct.unpack('<H', self.file_data[e_lfanew + 4:e_lfanew + 6])[0]
        self.num_sections = struct.unpack('<H', self.file_data[e_lfanew + 6:e_lfanew + 8])[0]
        opt_header_size = struct.unpack('<H', self.file_data[e_lfanew + 20:e_lfanew + 22])[0]

        # Parse optional header
        magic = struct.unpack('<H', self.file_data[e_lfanew + 24:e_lfanew + 26])[0]
        is_pe32_plus = (magic == 0x020B)

        # Entry point
        self.entry_point = struct.unpack('<I', self.file_data[e_lfanew + 40:e_lfanew + 44])[0]

        # ImageBase (offset 24 in optional header)
        if is_pe32_plus:
            self.image_base = struct.unpack('<Q', self.file_data[e_lfanew + 48:e_lfanew + 56])[0]
        else:
            self.image_base = struct.unpack('<I', self.file_data[e_lfanew + 52:e_lfanew + 56])[0]

        # Section alignment
        if is_pe32_plus:
            self.section_align = struct.unpack('<I', self.file_data[e_lfanew + 56:e_lfanew + 60])[0]
        else:
            self.section_align = struct.unpack('<I', self.file_data[e_lfanew + 52:e_lfanew + 56])[0]

        self.file_align = struct.unpack('<I', self.file_data[e_lfanew + 60:e_lfanew + 64])[0]

        # Parse section table
        section_table_offset = e_lfanew + 24 + opt_header_size

        for i in range(self.num_sections):
            offset = section_table_offset + i * 40
            name_bytes = self.file_data[offset:offset + 8]
            name = name_bytes.rstrip(b'\x00').decode('ascii', errors='ignore')

            virt_size = struct.unpack('<I', self.file_data[offset + 8:offset + 12])[0]
            virt_addr = struct.unpack('<I', self.file_data[offset + 12:offset + 16])[0]
            raw_size = struct.unpack('<I', self.file_data[offset + 16:offset + 20])[0]
            raw_addr = struct.unpack('<I', self.file_data[offset + 20:offset + 24])[0]
            characteristics = struct.unpack('<I', self.file_data[offset + 36:offset + 40])[0]

            section = {
                'index': i + 1,
                'name': name,
                'virtual_addr': virt_addr,
                'virtual_size': virt_size,
                'raw_addr': raw_addr,
                'raw_size': raw_size,
                'characteristics': characteristics
            }
            self.sections.append(section)
            self.section_map[i + 1] = section

        return self.sections

    def pdb_to_exe_va(self, pdb_section, pdb_offset):
        """Convert PDB address to EXE virtual address."""
        if pdb_section not in self.section_map:
            return None
        section = self.section_map[pdb_section]
        return self.image_base + section['virtual_addr'] + pdb_offset

    def pdb_to_exe_file_offset(self, pdb_section, pdb_offset):
        """Convert PDB address to EXE file offset."""
        if pdb_section not in self.section_map:
            return None
        section = self.section_map[pdb_section]
        return section['raw_addr'] + pdb_offset

    def get_section_info(self, pdb_section):
        """Get section information for a PDB section number."""
        return self.section_map.get(pdb_section)


class PDBFile:
    """Parser for PDB files - optimized for fast symbol lookup."""

    def __init__(self, filepath):
        """Initialize the PDB file parser."""
        self.filepath = filepath
        self.file_data = None
        self.file_size = 0

    def read_file(self):
        """Read the PDB file."""
        start = time.time()
        with open(self.filepath, 'rb') as f:
            self.file_data = f.read()
        self.file_size = len(self.file_data)
        # print(f"  Size: {self.file_size / 1024 / 1024:.2f} MB")
        # print(f"  Read time: {time.time() - start:.3f}s")
        return self.file_data

    def find_symbol(self, name):
        """Search for a symbol by name in the PDB file.

        Supports:
        - Simple function names: "my_function"
        - Class members: "Class::my_function"
        - Namespaced: "Namespace::Class::my_function"
        - Full path: "Outer::Inner::Class::my_function"

        Returns the first matching symbol.
        """
        results = self.find_all_symbols(name)
        return results[0] if results else None

    def find_all_symbols(self, name):
        """Find all symbols matching the given name (handles overloads).

        Supports:
        - Simple function names: "my_function" - finds all functions with this name
        - Class members: "Class::my_function"
        - Namespaced: "Namespace::Class::my_function"
        - Full path: "Outer::Inner::Class::my_function"

        Returns a list of all matching symbols.
        """
        start = time.time()
        results = []

        # Parse the input name to extract function name and qualifiers
        function_name = name
        qualifiers = []

        if '::' in name:
            parts = name.split('::')
            function_name = parts[-1]
            qualifiers = parts[:-1]

        # Build search patterns for MSVC mangled names
        # Format: ?function_name@class@namespace1@namespace2@@...
        # For input: Outer::Inner::Class::func
        # We build: ?func@Class@Inner@Outer@@
        patterns = []

        # 1. Global function: ?function_name@@
        patterns.append(('?' + function_name + '@@').encode('utf-8'))

        # 2. Class member with namespaces
        # Input qualifiers = [Outer, Inner, Class] from "Outer::Inner::Class::func"
        # MSVC mangled: ?func@Class@Inner@Outer@@
        # So we need to reverse qualifiers
        if qualifiers:
            parts_to_join = [function_name] + list(reversed(qualifiers))
            mangled = '?' + '@'.join(parts_to_join) + '@@'
            patterns.append(mangled.encode('utf-8'))

        # 3. Just the function name (fallback - will find class members too)
        patterns.append(function_name.encode('utf-8'))

        # Try each pattern
        for search_pattern in patterns:
            offset = 0
            while True:
                pos = self.file_data.find(search_pattern, offset)
                if pos == -1:
                    break

                # Look backwards for the symbol record
                for lookback in range(0, 100):
                    record_start = pos - lookback
                    if record_start < 0:
                        break

                    if record_start + 14 > len(self.file_data):
                        continue

                    rec_len = struct.unpack('<H', self.file_data[record_start:record_start + 2])[0]
                    rec_type = struct.unpack('<H', self.file_data[record_start + 2:record_start + 4])[0]

                    if rec_type not in [0x110E, 0x110C, 0x1108]:
                        continue

                    if rec_len < 10 or rec_len > 10000:
                        continue

                    offset_val = struct.unpack('<I', self.file_data[record_start + 8:record_start + 12])[0]
                    section = struct.unpack('<H', self.file_data[record_start + 12:record_start + 14])[0]

                    # Get the name
                    name_start = record_start + 14
                    name_end = self.file_data.find(b'\x00', name_start)
                    if name_end == -1:
                        continue

                    symbol_name = self.file_data[name_start:name_end].decode('utf-8', errors='ignore')

                    # Extract readable name
                    readable_name = symbol_name
                    if symbol_name.startswith('?'):
                        at_pos = symbol_name.find('@@')
                        if at_pos != -1:
                            readable_name = symbol_name[1:at_pos]

                    # Convert @ to :: for display
                    display_name = readable_name.replace('@', '::')

                    # Check if function name matches
                    parts = readable_name.split('@')
                    found_func = parts[0] if parts else ''

                    if found_func.lower() == function_name.lower():
                        # Check for duplicates
                        is_duplicate = False
                        for r in results:
                            if r['offset'] == offset_val and r['section'] == section:
                                is_duplicate = True
                                break

                        if not is_duplicate:
                            results.append({
                                'name': display_name,
                                'mangled_name': symbol_name,
                                'section': section,
                                'offset': offset_val,
                                'type': rec_type,
                                'file_offset': record_start
                            })

                        # For exact pattern match (like ?func@@), we only expect one result
                        if search_pattern.startswith(b'?' + function_name.encode() + b'@@'):
                            break

                offset = pos + 1

                # For exact patterns, don't continue searching
                if b'@@' in search_pattern and len(search_pattern) < len(function_name) + 10:
                    break

        # print(f"  Search time: {time.time() - start:.3f}s")
        return results


class PDBToEXEMapper:
    """Maps PDB symbols to EXE addresses."""

    def __init__(self, pdb_path, exe_path):
        """Initialize the mapper."""
        self.pdb = PDBFile(pdb_path)
        self.exe = PEFile(exe_path)

    def load_files(self):
        """Load and parse both PDB and EXE files."""
        # Load PDB
        self.pdb.read_file()
        # Load EXE
        self.exe.read_file()
        # Parse EXE
        self.exe.parse()

    def find_function(self, function_name):
        """Find a function and return its address information."""
        symbol = self.pdb.find_symbol(function_name)

        if not symbol:
            print(f"Function '{function_name}' not found in PDB")
            return None

        # print(f"Found in PDB:")
        # print(f"  Symbol Name: {symbol['name']}")
        # print(f"  Mangled:    {symbol['mangled_name']}")
        # print(f"  Section:    {symbol['section']}")
        # print(f"  Offset:     0x{symbol['offset']:08X} ({symbol['offset']:,})")
        # print(f"  Type:       0x{symbol['type']:04X}")

        # Get section info
        section_info = self.exe.get_section_info(symbol['section'])

        if not section_info:
            print(f"\nWarning: Section {symbol['section']} not found in EXE")
            return symbol

        # Calculate addresses
        exe_va = self.exe.pdb_to_exe_va(symbol['section'], symbol['offset'])
        exe_rva = exe_va - self.exe.image_base
        exe_file_offset = self.exe.pdb_to_exe_file_offset(symbol['section'], symbol['offset'])

        # print(f"\nMapped to EXE:")
        # print(f"  Section:    {section_info['name']}")
        # print(f"  Virtual Address (VA):  0x{exe_va:016X}")
        # print(f"  Relative VA (RVA):      0x{exe_rva:08X}")
        # print(f"  File Offset:          0x{exe_file_offset:08X}")

        # Add addresses to symbol dict
        symbol['exe_va'] = exe_va
        symbol['exe_rva'] = exe_rva
        symbol['exe_file_offset'] = exe_file_offset
        symbol['section_name'] = section_info['name']

        return symbol

    def search_functions(self, pattern, max_results=50):
        """Search for multiple functions matching a pattern."""
        print(f"\n=== Searching for functions matching: {pattern} ===")
        start = time.time()

        results = []
        seen_names = set()

        # Search in PDB file - lowercase once to avoid performance issue
        pdb_data_lower = self.pdb.file_data.lower()
        search_pattern = pattern.encode('utf-8').lower()
        offset = 0

        while len(results) < max_results:
            pos = pdb_data_lower.find(search_pattern, offset)
            if pos == -1:
                break

            # Look for symbol record
            for lookback in range(0, 100):
                record_start = pos - lookback
                if record_start < 0:
                    break

                if record_start + 14 > len(self.pdb.file_data):
                    continue

                rec_len = struct.unpack('<H', self.pdb.file_data[record_start:record_start + 2])[0]
                rec_type = struct.unpack('<H', self.pdb.file_data[record_start + 2:record_start + 4])[0]

                if rec_type not in [0x110E, 0x110C]:
                    continue

                if rec_len < 10 or rec_len > 10000:
                    continue

                offset_val = struct.unpack('<I', self.pdb.file_data[record_start + 8:record_start + 12])[0]
                section = struct.unpack('<H', self.pdb.file_data[record_start + 12:record_start + 14])[0]

                name_start = record_start + 14
                name_end = self.pdb.file_data.find(b'\x00', name_start)
                if name_end == -1:
                    continue

                symbol_name = self.pdb.file_data[name_start:name_end].decode('utf-8', errors='ignore')

                readable_name = symbol_name
                if symbol_name.startswith('?'):
                    at_pos = symbol_name.find('@@')
                    if at_pos != -1:
                        readable_name = symbol_name[1:at_pos]

                if readable_name not in seen_names and pattern.lower() in readable_name.lower():
                    seen_names.add(readable_name)

                    section_info = self.exe.get_section_info(section)
                    if section_info:
                        exe_va = self.exe.pdb_to_exe_va(section, offset_val)
                        exe_rva = exe_va - self.exe.image_base if exe_va else None
                        exe_file_offset = self.exe.pdb_to_exe_file_offset(section, offset_val)
                    else:
                        exe_va = None
                        exe_rva = None
                        exe_file_offset = None

                    results.append({
                        'name': readable_name,
                        'section': section,
                        'offset': offset_val,
                        'exe_va': exe_va,
                        'exe_rva': exe_rva,
                        'exe_file_offset': exe_file_offset,
                        'section_name': section_info['name'] if section_info else '?'
                    })

                    break

            offset = pos + 1

        # print(f"  Search time: {time.time() - start:.3f}s")
        return results

    def print_mapping_rules(self):
        """Print the address mapping rules."""
        print("\n" + "=" * 100)
        print("Address Mapping Rules")
        print("=" * 100)

        print("\n1. PDB Address Format:")
        print("   PDB addresses are stored as: Section Number (1-based) + Offset within section")

        print("\n2. EXE Virtual Address (VA):")
        print("   EXE_VA = ImageBase + Section.VirtualAddress + PDB_Offset")
        print(f"   ImageBase: 0x{self.exe.image_base:016X}")

        print("\n3. EXE Relative Virtual Address (RVA):")
        print("   EXE_RVA = EXE_VA - ImageBase")
        print("         = Section.VirtualAddress + PDB_Offset")

        print("\n4. EXE File Offset:")
        print("   EXE_FileOffset = Section.RawAddr + PDB_Offset")

        print("\n5. Section Mapping:")
        print("   PDB Section numbers map 1-to-1 to PE Section Table order:")
        for i, section in enumerate(self.exe.sections):
            flags = []
            if section['characteristics'] & 0x00000020: flags.append('CODE')
            if section['characteristics'] & 0x10000000: flags.append('EXEC')
            if section['characteristics'] & 0x40000000: flags.append('READ')
            if section['characteristics'] & 0x80000000: flags.append('WRITE')
            print(f"   PDB Section {i + 1} = PE Section '{section['name']}' ({' '.join(flags)})")

        print("=" * 100)


def main():
    """Main function."""
    pdb_path = "blender.pdb"
    exe_path = "blender.exe"

    # Create mapper
    mapper = PDBToEXEMapper(pdb_path, exe_path)

    # Load files
    mapper.load_files()

    # Print mapping rules (comment out for speed)
    # mapper.print_mapping_rules()

    # Find target function
    target = "GPU_shader_get_builtin_shader"
    result = mapper.find_function(target)

    if result:
        print("\n" + "=" * 100)
        print("FINAL RESULT")
        print("=" * 100)
        print(f"\nFunction: {result['name']}")
        print(f"PDB Section: {result['section']} ({result['section_name']})")
        print(f"PDB Offset:  0x{result['offset']:08X}")
        print(f"\nEXE Addresses:")
        print(f"  Virtual Address (VA): 0x{result['exe_va']:016X}")
        print(f"  Relative VA (RVA):      0x{result['exe_rva']:08X}")
        print(f"  File Offset:          0x{result['exe_file_offset']:08X}")
        print("=" * 100)

    # Search for related functions - comment out for speed
    # print(f"\n=== Searching for GPU_shader* functions ===")
    # results = mapper.search_functions("GPU_shader", max_results=20)
    # if results:
    #     print(f"\nFound {len(results)} GPU_shader functions:\n")
    #     print(f"{'Function Name':<60} {'Section':<10} {'EXE RVA':<12}")
    #     print("-" * 90)
    #     for r in results:
    #         name = r['name']
    #         if len(name) > 58:
    #             name = name[:55] + "..."
    #         rva_str = f"0x{r['exe_rva']:08X}" if r['exe_va'] else "N/A"
    #         print(f"{name:<60} {r['section_name']:<10} {rva_str:<12}")

    # print(f"\nTotal runtime: {time.time() - mapper_start_time:.3f}s")


if __name__ == "__main__":
    mapper_start_time = time.time()
    main()
