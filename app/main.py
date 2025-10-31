import sys
import os
import zlib
import hashlib
import time
import datetime
import argparse
from urllib import request
import re
import io # <-- NEW IMPORT

class Git:
    # hard coding - reusability - ALL_CAPS - convention variable name
    OBJECTS_DIR = 'objects'
    REFS_DIR = 'refs'
    HEAD_FILE = 'HEAD'
    HEADS_DIR = 'heads'
    
    # Pack file object types
    OBJ_COMMIT = 1
    OBJ_TREE = 2
    OBJ_BLOB = 3
    OBJ_TAG = 4
    OBJ_OFS_DELTA = 6
    OBJ_REF_DELTA = 7

    def __init__(self, git_dir = '.git'):
        self.git_dir = git_dir


    # -------- GIT COMMANDS --------

    # -- 1. COMMAND : git init --
    def init(self, args): 
        os.makedirs(os.path.join(self.git_dir, Git.OBJECTS_DIR), exist_ok=True)
        os.makedirs(os.path.join(self.git_dir, Git.REFS_DIR, Git.HEADS_DIR), exist_ok=True)
        head_file_path = os.path.join(self.git_dir, Git.HEAD_FILE)
        
        if not os.path.exists(head_file_path):
            with open(head_file_path, 'w') as f:
                f.write(f"ref: {os.path.join(Git.REFS_DIR, Git.HEADS_DIR)}/main\n")
        print("Initialized git directory")


    # -- 2. COMMAND : git cat-file <flag> <hash-of-the-file> --
    def cat_file(self, args): 
        hash_str = args.object_hash
        object_path = os.path.join(self.git_dir, Git.OBJECTS_DIR, hash_str[:2], hash_str[2:]) 
        content = self._get_object_content(object_path)

        if content is None:
            print(f"fatal: Not a valid object name {hash_str}", file=sys.stderr)
            sys.exit(1)

        header, _ , body = content.partition(b'\x00')
        type_str, _ , size_str = header.partition(b'\x20')
            
        if args.p:
            print(body.decode('utf-8'), end='') 
        elif args.t:
            print(type_str.decode('utf-8'), end='')
        elif args.s:
            print(size_str.decode('utf-8'), end='')
        else:
            print("Usage: cat-file <flag> <hash-of-object>", file=sys.stderr)


    # -- 3. COMMAND: git hash-object <flag> <file-name> -- 
    def hash_object(self, args):
        if not os.path.exists(args.file_path):
            print(f"fatal: file does not exist.")
            sys.exit(1)
        sha1 = self._write_blob(args.file_path, args.w)
        print(sha1)


    # -- 4. Command - git ls-tree <flag> <tree-sha> -- 
    def ls_tree(self, args):
        hash_of_tree_object = args.tree_hash
        content = self._get_object(hash_of_tree_object, 'tree')
        
        if content is None:
            print(f"fatal: {hash_of_tree_object} is not a tree object", file=sys.stderr)
            sys.exit(1)

        body_start = content.find(b'\x00') + 1
        tree_entries = content[body_start:]
        i = 0

        while i < len(tree_entries):
            space_index = tree_entries.find(b'\x20', i)
            mode = tree_entries[i : space_index]
            
            null_index = tree_entries.find(b'\x00', space_index)
            filename = tree_entries[space_index + 1: null_index]
            
            sha1_start = null_index + 1
            sha1 = tree_entries[sha1_start: sha1_start + 20]
            i = sha1_start + 20

            if args.name_only:
                print(filename.decode('utf-8'))
            else:
                mode_str = mode.decode('ascii')
                if mode_str == '100644' or mode_str == '100755':
                    type_str = 'blob'
                elif mode_str == '40000':
                    type_str = 'tree'
                else:
                    type_str = 'unknown'

                print(f"{mode.decode('utf-8')} {type_str} {sha1.hex()}\t{filename.decode('utf-8')}")


    # -- 5. SubCommand - git write-tree --
    def write_tree(self, args, directory_path = '.'):
        tree_entries_str = b''
        entries = []
        dir_path = directory_path

        try:
            contents = os.listdir(dir_path)
            filtered_contents = [ name for name in contents if name not in ('.git', '.', '..')]

            if not filtered_contents:
                tree_object = b'tree 0\x00'
                return self._compute_sha1_hash(tree_object)

            for object_name in filtered_contents:
                object_path = os.path.join(directory_path, object_name)
                if os.path.isfile(object_path):
                    blob_sha1_hex = self._write_blob(object_path, True)
                    blob_sha1_bytes = bytes.fromhex(blob_sha1_hex)
                    mode_str = '100755' if os.access(object_path, os.X_OK) else '100644'
                    entries.append((object_name, mode_str.encode('ascii') + b'\x20' + object_name.encode('utf-8') + b'\x00' + blob_sha1_bytes))
                elif os.path.isdir(object_path):
                    sub_tree_sha_hex = self.write_tree(args, object_path)
                    entries.append((object_name + '/', b'40000' + b'\x20' + object_name.encode('utf-8') + b'\x00' + bytes.fromhex(sub_tree_sha_hex)))

            entries.sort()
            for entry in entries:
                tree_entries_str += entry[1]
            
            tree_content = b'tree ' + str(len(tree_entries_str)).encode('ascii') + b'\x00' + tree_entries_str
            tree_sha = self._write_object(tree_content, None) # _write_object adds header

            if dir_path == '.':
                print(tree_sha)
            return tree_sha

        except FileNotFoundError:
            print(f"Error: Directory {dir_path} not found.", file=sys.stderr)
            sys.exit(1)


    # -- 6. SubCommand - git commit-tree <tree-sha> -p <parent-commit-sha> -m <commit-message> --
    def commit_tree(self, args):
        commiter_name = 'utsavgoyal'
        commiter_email = 'goyalutsav2004@gmail.com'
        
        current_time = int(time.time())
        offset_seconds = time.altzone if time.daylight else time.timezone
        offset_hours = abs(offset_seconds) // 3600
        offset_minutes = (abs(offset_seconds) % 3600) // 60
        sign = '-' if offset_seconds > 0 else '+'
        timezone_offset = f"{sign}{offset_hours:02}{offset_minutes:02}"
        final_timestamp_string = f"{current_time} {timezone_offset}"

        tree_sha = args.tree_hash
        parent_sha = args.parent
        identity = f"{commiter_name} <{commiter_email}> {final_timestamp_string}"

        lines = [f"tree {tree_sha}"]
        if parent_sha:
            lines.append(f"parent {parent_sha}")
        lines.extend([
            f"author {identity}",
            f"committer {identity}",
            "",
            args.message,
        ])   
        commit_content = "\n".join(lines) + "\n"
        
        sha_of_commit_object = self._write_object(commit_content.encode('utf-8'), 'commit')
        print(sha_of_commit_object)

    
    # -- 7. Subcommand - git clone <github-repo-https> <dir-to-clone-to>
    def clone(self, args):
        repo_url = args.repo_address
        directory_name = args.directory_name

        try:
            if not os.path.exists(directory_name):
                os.makedirs(directory_name)
            elif not os.path.isdir(directory_name):
                print(f"fatal: '{directory_name}' exists but is not a directory.", file=sys.stderr)
                sys.exit(1)
            elif os.listdir(directory_name):
                 print(f"fatal: '{directory_name}' exists and is not empty.", file=sys.stderr)
                 sys.exit(1)

            os.chdir(directory_name)
            self.git_dir = os.path.join(os.getcwd(), '.git')

            self.init(args) 
            print(f"Initialized empty Git repository in {self.git_dir}/")
        except Exception as e:
            print(f"Error creating directory or initializing repo: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"Cloning into '{directory_name}'...")

        ref_discovery_url = f"{repo_url.rstrip('/')}/info/refs?service=git-upload-pack"
        try:
            with request.urlopen(ref_discovery_url) as response:
                if response.status != 200:
                    raise Exception(f"HTTP Error {response.status}: {response.reason}")
                response_bytes = response.read()
        except Exception as e:
            print(f"fatal: could not read from remote repository: {e}", file=sys.stderr)
            sys.exit(1)

        refs, capabilities = self._parse_pkt_lines(response_bytes)
        
        head_sha = ""
        head_ref = ""
        if 'refs/heads/main' in refs:
            head_ref = 'refs/heads/main'
        elif 'refs/heads/master' in refs:
            head_ref = 'refs/heads/master'
        else:
            print("fatal: could not find 'main' or 'master' branch", file=sys.stderr)
            sys.exit(1)
        head_sha = refs[head_ref]

        upload_pack_url = f"{repo_url.rstrip('/')}/git-upload-pack"
        post_data = b""
        post_data += self._create_pkt_line(f"want {head_sha}\n")
        post_data += self._create_pkt_line(None, flush=True)
        post_data += self._create_pkt_line("done\n")

        try:
            post_req = request.Request(upload_pack_url, data=post_data, headers={
                'Content-Type': 'application/x-git-upload-pack-request',
                'Accept': 'application/x-git-upload-pack-result',
            })
            with request.urlopen(post_req) as response:
                if response.status != 200:
                    raise Exception(f"HTTP Error {response.status}: {response.reason}")
                pack_file_data = response.read()
        except Exception as e:
            print(f"fatal: could not fetch PACK file: {e}", file=sys.stderr)
            sys.exit(1)
        
        pack_start_index = pack_file_data.find(b'PACK')
        if pack_start_index == -1:
            print("fatal: 'PACK' header not found in response", file=sys.stderr)
            sys.exit(1)
            
        # The first 8 bytes of the pack data are "NAK\n" or similar side-band data
        # We find the *actual* start of the pack data by looking for b'PACK'
        binary_pack_data = pack_file_data[pack_start_index:]
        
        # --- PARSE, WRITE, and CHECKOUT ---
        self._parse_pack_file(binary_pack_data, head_sha)
        self._update_refs(head_sha, head_ref)
        
        commit = self._get_object(head_sha, 'commit')
        tree_sha = re.search(b'tree ([a-f0-9]{40})', commit).group(1).decode('ascii')
        
        self._checkout_files(tree_sha, '.')
        print(f"Successfully cloned and checked out branch.")
        

    # -------- HELPER FUNCTIONS --------

    # 1. Reading and Decompress a zlib-compressed object file
    def _get_object_content(self, file_path):
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, 'rb') as f:
                compressed_data = f.read()
            return zlib.decompress(compressed_data)
        except (zlib.error, Exception):
            return None
        
    def _get_object(self, sha: str, expected_type: str = None):
        """Helper to read an object from the DB and verify its type."""
        object_path = os.path.join(self.git_dir, Git.OBJECTS_DIR, sha[:2], sha[2:])
        content = self._get_object_content(object_path)
        if content is None:
            return None
            
        header, _, body = content.partition(b'\x00')
        type_str, _, size_str = header.partition(b'\x20')
        
        if expected_type and type_str.decode('utf-8') != expected_type:
            return None
        return content


    # 2. Computing sha1 hash 
    def _compute_sha1_hash(self, input_bytes: bytes): 
        sha1_hash = hashlib.sha1()
        sha1_hash.update(input_bytes)
        return sha1_hash.hexdigest()
    

    # 3. Reading, hashing, compressing, and optionally writing
    def _write_blob(self, file_path: str, write_to_disk: bool) -> str:
        try:
            with open(file_path, 'rb') as f:
                file_content_bytes= f.read()
        except Exception as e:
            print(f"Error in reading the file: {e}", file=sys.stderr)
            sys.exit(1)

        if not write_to_disk:
            # Need to compute hash even if not writing
            header_bytes = f"blob {len(file_content_bytes)}\x00".encode('ascii')
            full_content = header_bytes + file_content_bytes
            return self._compute_sha1_hash(full_content)

        return self._write_object(file_content_bytes, 'blob')


    # 4. Write any object content (with header) to the DB
    def _write_object(self, content_bytes: bytes, obj_type: str) -> str:
        """Writes raw object content to the object DB, adding the header."""
        
        # If obj_type is None, assume content_bytes already includes the header
        if obj_type is None:
            full_content = content_bytes
        else:
            header_bytes = f"{obj_type} {len(content_bytes)}\x00".encode('ascii')
            full_content = header_bytes + content_bytes
        
        sha1_of_file = self._compute_sha1_hash(full_content)
        
        path_new_object_dir = os.path.join(self.git_dir, Git.OBJECTS_DIR , sha1_of_file[:2])
        os.makedirs(path_new_object_dir, exist_ok=True)

        path_new_object = os.path.join(path_new_object_dir, sha1_of_file[2:])
        if not os.path.exists(path_new_object):
            try:
                with open(path_new_object, 'wb') as f:
                    f.write(zlib.compress(full_content))
            except Exception as e:
                print(f"Error while writing to file: {e}", file=sys.stderr)
                sys.exit(1)
        return sha1_of_file

    # 5. Create a pkt-line
    def _create_pkt_line(self, data_str: str, flush: bool = False) -> bytes:
        if flush or data_str is None:
            return b'0000'
        data_bytes = data_str.encode('utf-8')
        length = len(data_bytes) + 4
        hex_length = f"{length:04x}"
        return hex_length.encode('utf-8') + data_bytes

    # 6. Parse a pkt-line response
    def _parse_pkt_lines(self, response_bytes: bytes):
        refs = {}
        capabilities = []
        i = 0
        is_first_ref_line = True

        while i < len(response_bytes):
            hex_length = response_bytes[i:i+4].decode('utf-8')
            if hex_length == '0000':
                i += 4
                continue 
            
            length = int(hex_length, 16)
            if length == 0:
                i += 4
                continue
                
            line_content = response_bytes[i+4 : i+length]
            line_str = line_content.decode('utf-8').strip()
            i += length 

            if line_str.startswith("# service="):
                continue
            
            sha, ref_part = line_str.split(' ', 1)
            
            if is_first_ref_line:
                if '\x00' in ref_part:
                    ref_name, caps_str = ref_part.split('\x00', 1)
                    refs[ref_name] = sha
                    capabilities = caps_str.split(' ')
                    is_first_ref_line = False
                else:
                    refs[ref_part] = sha
            else:
                refs[ref_part] = sha
                    
        return refs, capabilities

    # 7. Parse the downloaded PACK file
    def _parse_pack_file(self, data: bytes, head_sha: str):
        f = io.BytesIO(data)
        
        # Read PACK header
        pack_sig, version, num_objects = self._read_pack_header(f)
        
        objects = {}  # Store objects for delta resolution
        
        for _ in range(num_objects):
            # Read object header
            obj_type, obj_size, ofs = self._read_pack_object_header(f)
            
            decompressed_data = b""
            decompressor = zlib.decompressobj()
            
            # Robust handling of decompression
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                
                try:
                    decompressed_data += decompressor.decompress(chunk)
                    
                    # If decompression reaches EOF or has unused data, stop
                    if decompressor.unused_data or decompressor.eof:
                        f.seek(f.tell() - len(decompressor.unused_data))
                        break
                except zlib.error as e:
                    print(f"Decompression error at offset {ofs}: {e}", file=sys.stderr)
                    break
            
            # Processing the object based on its type
            if obj_type == Git.OBJ_COMMIT:
                objects[ofs] = (obj_type, decompressed_data, None)
            elif obj_type == Git.OBJ_TREE:
                objects[ofs] = (obj_type, decompressed_data, None)
            elif obj_type == Git.OBJ_BLOB:
                objects[ofs] = (obj_type, decompressed_data, None)
            elif obj_type == Git.OBJ_OFS_DELTA:
                delta_stream = io.BytesIO(decompressed_data)
                offset_data = delta_stream.read(1)
                offset = offset_data[0] & 0x7F
                while offset_data[0] & 0x80:
                    offset_data = delta_stream.read(1)
                    offset = ((offset + 1) << 7) | (offset_data[0] & 0x7F)
                
                base_obj_offset = ofs - offset
                delta_instructions = delta_stream.read()
                
                objects[ofs] = (obj_type, delta_instructions, base_obj_offset)
                continue # Skip writing, will resolve deltas later
            else:
                print(f"Unsupported object type {obj_type}", file=sys.stderr)
                continue

        # Resolve deltas and write objects
        for ofs, (obj_type, data, base_info) in objects.items():
            if obj_type == Git.OBJ_OFS_DELTA:
                base_obj_offset = base_info
                
                # Ensure base object is already resolved (can be a delta itself)
                base_type, base_data, _ = objects[base_obj_offset]
                while base_type == Git.OBJ_OFS_DELTA:
                    # This base is *also* a delta. Recurse.
                    (base_type, base_data, base_info) = objects[base_info]
                    
                # Apply patch
                patched_data = self._apply_delta(base_data, data) # `data` is the instructions
                
                # Determine type of patched object
                if base_type == Git.OBJ_COMMIT:
                    final_type_str = "commit"
                elif base_type == Git.OBJ_TREE:
                    final_type_str = "tree"
                elif base_type == Git.OBJ_BLOB:
                    final_type_str = "blob"
                
                # Write the new, patched object and update its entry
                sha = self._write_object(patched_data, final_type_str)
                objects[ofs] = (base_type, patched_data, None) # Now it's a base object
            
            elif obj_type in [Git.OBJ_COMMIT, Git.OBJ_TREE, Git.OBJ_BLOB]:
                # Write base objects
                self._write_object(data, "commit" if obj_type == Git.OBJ_COMMIT else ("tree" if obj_type == Git.OBJ_TREE else "blob"))

                
    # 8. Read PACK file header
    def _read_pack_header(self, f):
        # 4-byte signature 'PACK'
        pack_sig = f.read(4)
        if pack_sig != b'PACK':
            raise Exception("Not a PACK file")
        
        # 4-byte version number (should be 2)
        version = int.from_bytes(f.read(4), 'big')
        if version != 2:
            raise Exception(f"Unsupported PACK version {version}")
        
        # 4-byte number of objects
        num_objects = int.from_bytes(f.read(4), 'big')
        
        return pack_sig, version, num_objects
        
    # 9. Read a PACK file object header
    def _read_pack_object_header(self, f):
        """Reads the variable-length object header, returns type and size."""
        ofs = f.tell()
        byte = f.read(1)[0]
        
        obj_type = (byte >> 4) & 0x07
        size = byte & 0x0F
        
        shift = 4
        while byte & 0x80: # MSB is 1, more bytes to read
            byte = f.read(1)[0]
            size |= (byte & 0x7F) << shift
            shift += 7
            
        return obj_type, size, ofs
    
    # 10. Apply a delta patch
    def _apply_delta(self, base_data, delta_data):
        """Applies a git delta to a base object."""
        delta_stream = io.BytesIO(delta_data)
        
        # Read and check source size
        source_size = 0
        byte = delta_stream.read(1)[0]
        shift = 0
        while byte & 0x80:
            source_size |= (byte & 0x7F) << shift
            shift += 7
            byte = delta_stream.read(1)[0]
        source_size |= (byte & 0x7F) << shift
        
        if source_size != len(base_data):
            raise Exception("Delta source size does not match base object size")

        # Read and check target size
        target_size = 0
        byte = delta_stream.read(1)[0]
        shift = 0
        while byte & 0x80:
            target_size |= (byte & 0x7F) << shift
            shift += 7
            byte = delta_stream.read(1)[0]
        target_size |= (byte & 0x7F) << shift
        
        target_data = io.BytesIO()
        
        while True:
            cmd_byte = delta_stream.read(1)
            if not cmd_byte:
                break
            cmd = cmd_byte[0]
            
            if cmd & 0x80: # Copy instruction
                offset = 0
                length = 0
                
                if cmd & 0x01: offset |= delta_stream.read(1)[0] << 0
                if cmd & 0x02: offset |= delta_stream.read(1)[0] << 8
                if cmd & 0x04: offset |= delta_stream.read(1)[0] << 16
                if cmd & 0x08: offset |= delta_stream.read(1)[0] << 24
                
                if cmd & 0x10: length |= delta_stream.read(1)[0] << 0
                if cmd & 0x20: length |= delta_stream.read(1)[0] << 8
                if cmd & 0x40: length |= delta_stream.read(1)[0] << 16
                
                if length == 0: length = 0x10000 # 0 means 65536
                    
                target_data.write(base_data[offset:offset+length])
                
            elif cmd > 0: # Insert instruction
                target_data.write(delta_stream.read(cmd))
            
            else:
                raise Exception("Invalid delta command")
        
        final_data = target_data.getvalue()
        if len(final_data) != target_size:
            raise Exception("Delta result size does not match target size")
            
        return final_data
        
    # 11. Update local refs (HEAD, refs/heads/main)
    def _update_refs(self, head_sha: str, head_ref: str):
        # Write the ref for the branch
        branch_name = head_ref.split('/')[-1]
        ref_path = os.path.join(self.git_dir, Git.REFS_DIR, Git.HEADS_DIR, branch_name)
        os.makedirs(os.path.dirname(ref_path), exist_ok=True)
        with open(ref_path, 'w') as f:
            f.write(head_sha + '\n')
            
        # Update HEAD to point to this new branch
        with open(os.path.join(self.git_dir, Git.HEAD_FILE), 'w') as f:
            f.write(f"ref: {head_ref}\n")

    # 12. Checkout files from a tree
    def _checkout_files(self, tree_sha: str, base_path: str):
        """Recursively checks out files from a tree."""
        tree_content = self._get_object(tree_sha, 'tree')
        if tree_content is None:
            return
            
        body_start = tree_content.find(b'\x00') + 1
        tree_entries = tree_content[body_start:]
        
        i = 0
        while i < len(tree_entries):
            space_index = tree_entries.find(b'\x20', i)
            mode = tree_entries[i : space_index].decode('ascii')
            
            null_index = tree_entries.find(b'\x00', space_index)
            filename = tree_entries[space_index + 1: null_index].decode('utf-8')
            
            sha1 = tree_entries[null_index + 1: null_index + 21].hex()
            i = null_index + 21
            
            current_path = os.path.join(base_path, filename)
            
            if mode == '40000': # Directory
                os.makedirs(current_path, exist_ok=True)
                self._checkout_files(sha1, current_path)
            else: # File (blob)
                blob_content = self._get_object(sha1, 'blob')
                blob_body_start = blob_content.find(b'\x00') + 1
                with open(current_path, 'wb') as f:
                    f.write(blob_content[blob_body_start:])
                
                # Set permissions (100755 or 100644)
                if mode == '100755':
                    os.chmod(current_path, 0o755)
                else:
                    os.chmod(current_path, 0o644)


# -------- MAIN ---------

def main():
    git = Git()
    parser = argparse.ArgumentParser(description="Basic Git Implementation.")
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title="Avialable commands"
    )

    init_parser = subparsers.add_parser('init', help="initiliase a new Git repo")
    init_parser.set_defaults(func=git.init)

    cat_file_parser = subparsers.add_parser('cat-file', help="reading the content of a Git object")
    group = cat_file_parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-p', action='store_true', help='Pretty print the contents of the object')
    group.add_argument('-t', action='store_true', help='print the type of object')
    group.add_argument('-s', action='store_true', help="print byte size of the object")
    cat_file_parser.add_argument('object_hash', type=str, help="sha1-hash of the Git object to read")
    cat_file_parser.set_defaults(func=git.cat_file)

    hash_object_parser = subparsers.add_parser('hash-object', help="Computing the sha-1 hash of git object, and optionally storing the object to Git database")
    hash_object_parser.add_argument('-w', action='store_true', help="Storing the object to Git database")
    hash_object_parser.add_argument('file_path', help="file path to caculate the sha1-hash of")
    hash_object_parser.set_defaults(func=git.hash_object)

    ls_tree_parser = subparsers.add_parser('ls-tree', help='list the content of a tree object')
    ls_tree_parser.add_argument("tree_hash", type=str, help='SHA-1 hash of the tree object to read')
    ls_tree_parser.add_argument('--name-only', dest='name_only', action='store_true', help='Only print the names of the item')
    ls_tree_parser.set_defaults(func = git.ls_tree)

    write_tree_parser = subparsers.add_parser('write-tree', help='creates a tree object from the current state of the staging area.')
    write_tree_parser.set_defaults(func = git.write_tree)

    commit_tree_parser = subparsers.add_parser('commit-tree', help="creating a commit object")
    commit_tree_parser.add_argument("tree_hash", type=str, help="SHA-1 hash of the tree object (snapshot root)")
    commit_tree_parser.add_argument('-p', '--parent', type=str, action='store', help="SHA-1 hash of parent commit")
    commit_tree_parser.add_argument('-m', '--message', type=str, action='store', required=True, help="Commit message")
    commit_tree_parser.set_defaults(func= git.commit_tree)

    clone_parser = subparsers.add_parser("clone", help="Cloning a public repository from Github")
    clone_parser.add_argument("repo_address", type=str, help="The URL or path to the repo to clone")
    clone_parser.add_argument("directory_name", type=str, help="The path to the directory to clone into")
    clone_parser.set_defaults(func=git.clone)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()