# BYO - GIT

import sys
import os
import zlib
import hashlib
import time
import datetime
import argparse
import urllib.request
import struct

class Git:
    # hard coding - reusability - ALL_CAPS - convention variable name
    OBJECTS_DIR = 'objects'
    REFS_DIR = 'refs'
    HEAD_FILE = 'HEAD'
    HEADS_DIR = 'heads'

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
        # creating necessary directories - objects and refs/heads
        os.makedirs(os.path.join(self.git_dir, Git.OBJECTS_DIR), exist_ok=True)
        os.makedirs(os.path.join(self.git_dir, Git.REFS_DIR, Git.HEADS_DIR), exist_ok=True)

        # writing to head file
        with open(os.path.join(self.git_dir, Git.HEAD_FILE), 'w') as f:
            f.write(f"ref: {os.path.join(Git.REFS_DIR, Git.HEADS_DIR)}/main\n")

        print("Initialized git directory")


    # -- 2. COMMAND : git cat-file <flag> <hash-of-the-file> --
    def cat_file(self, args): 
        sha = args.object_hash
        object_path = self._object_path(sha) # the object associated with the given hash
        
        # Need content of file at the path - zlib decompression
        content = self._get_object_content(object_path)

        # Content format - <object-type>\x20<size>\x00<content>
        if content is None:
            print(f"fatal: Not a valid object name {sha}", file=sys.stderr)
            sys.exit(1)

        header, _ , body = content.partition(b'\x00')
        type, _ , size = header.partition(b'\x20')
            
        if args.p:
            print(body.decode('utf-8'), end='') # content byte -> string 
        elif args.t:
            print(type.decode('utf-8'), end='')
        elif args.s:
            print(size.decode('utf-8'), end='')
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

        # given sha - we know path - decompress - work on --name-only - parse the names 
        hash_of_tree_object = args.tree_hash
        path_to_tree_object = self._object_path(hash_of_tree_object)
        content_of_tree_object = self._get_object_content(path_to_tree_object)

        if content_of_tree_object is None:
            print(f"fatal: Not a valid object name: {hash_of_tree_object}", file=sys.stderr)
            sys.exit(1)

        header , _ , body = content_of_tree_object.partition(b'\x00')

        if not header.startswith(b'tree '):
            print(f"fatal: {hash_of_tree_object} is not a tree object", file=sys.stderr)
            sys.exit(1)

        # Parsing of each entry needed
        tree_entries = body
        i = 0

        # format  - <mode>\x20<filename>\x00<sha1-hash>
        while i < len(tree_entries):

            # first component - mode
            space_index = tree_entries.find(b'\x20', i)
            if space_index == -1: break # should not happend in a valid tree

            mode = tree_entries[i : space_index]

            # second Component - filename
            filename_start = space_index + 1
            null_index = tree_entries.find(b'\x00', space_index)
            if null_index == -1 : break # not a valid tree
            filename = tree_entries[filename_start: null_index]

            # third component - sha1 hash
            sha1_start = null_index + 1
            sha1 = tree_entries[sha1_start: sha1_start + 20]

            if args.name_only:
                # currently we need to print only the file name
                print(filename.decode('utf-8'))

            else:
                mode_str = mode.decode('ascii')
                if mode_str == '100644' or mode_str == '100755' or mode_str == '120000' or mode_str == '160000':
                    type = 'blob'
                elif mode_str == '40000':
                    type = 'tree'
                else:
                    type = 'unknown' # cases of symlinks and other cases

                sha1_hex_string = sha1.hex()

                to_print = mode.decode('utf-8') + '\t' + type + '\t' + sha1_hex_string + '\t' + filename.decode('utf-8')

                print(to_print)

            i = sha1_start + 20


    # -- 5. SubCommand - git write-tree --
    def write_tree(self, args, directory_path = '.'):
        tree_entries_str = b''
        entries = []

        # Iterating over the Dir
        dir_path = directory_path

        try:
            contents = os.listdir(dir_path)

            # critical step - ignoring .git directory
            filtered_contents = [ name for name in contents 
                                if name not in ('.git', '.', '..')]

            if not filtered_contents:
                # empty directory
                tree_object = b'tree 0\x00'
                return self._write_object(tree_object)

            for object in filtered_contents:
                object_path = os.path.join(directory_path, object)
                if os.path.isfile(object_path):
                    # Need - sha1 hash(20 byte), mode, filename
                    blob_sha1_hex = self._write_blob(object_path, True)
                    blob_sha1_bytes = bytes.fromhex(blob_sha1_hex)
                    # Mode - according to git standards -  not the os full permissions
                    if os.access(object_path, os.X_OK):
                        mode_str = '100755'
                    else:
                        mode_str = '100644'
                    
                    # appending tuple(filename, object) to sort later on alphabetically
                    entries.append((object, mode_str.encode('ascii') + b'\x20' + object.encode('utf-8') + b'\x00' + blob_sha1_bytes))

                elif os.path.isdir(object_path):
                    sub_tree_sha_hex = self.write_tree(args, object_path)
                    entries.append((object + '/', b'40000' + b'\x20' + object.encode('utf-8') + b'\x00' + bytes.fromhex(sub_tree_sha_hex)))

            entries.sort()
            for entry in entries:
                tree_entries_str += entry[1]
            size_of_tree_object = len(tree_entries_str)
            tree_object = b'tree ' + str(size_of_tree_object).encode('ascii') + b'\x00' + tree_entries_str

            tree_sha = self._write_object(tree_object)

            if dir_path == '.':
                print(tree_sha)
            return tree_sha

        except FileNotFoundError:
            print(f"Error: Directory {dir_path} not found.", file=sys.stderr)
            sys.exit(1)


    # -- 6. SubCommand - git commit-tree <tree-sha> -p <parent-commit-sha> -m <commit-message> --
    def commit_tree(self, args):
        # To do: Create commit content -> generate sha -> make a commit object -> print the sha

        # hardcoding the name and email
        commiter_name = 'utsavgoyal'
        commiter_email = 'goyalutsav2004@gmail.com'
        
        # time format - epoch timestamp + the timezone offset
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
        commit_content_bytes = commit_content.encode('utf-8')
        
        commit_object_content = (
            b'commit ' + str(len(commit_content_bytes)).encode('ascii') + b'\x00' + commit_content_bytes
        )

        sha_of_commit_object = self._write_object(commit_object_content)

        print(sha_of_commit_object)

    
    # -- 7. Subcommand - git clone <github-repo-https> <dir-to-clone-to>
    def clone(self, args):
        repo_url = args.repo_address
        target_dir = args.directory_name

        os.makedirs(target_dir, exist_ok=True) # creating a target clone folder
        self.git_dir = os.path.join(target_dir, '.git') # redirecting all object writes to new clone git 
        self.init(args)

        # GET request to get refs
        data = self._discover_refs(repo_url)
        lines = self._parse_pkt_lines(data)

        # for testing
        # for line in lines: 
        #     print(line)

        # Extracting the SHA of head commit - eg main branch
        head_commit_sha = self._get_head_commit_sha(lines)

        # Asking for PACK data using POST request and head commit sha
        pack_data = self._request_pack(repo_url, head_commit_sha.encode('ascii'))

        # extracting pack bytes - pack_data = pkt line + pack bytes
        pack_bytes = self._extract_pack_bytes(pack_data)

        version, object_count = self._parse_pack_header(pack_bytes)

        # testing
        # print(f"version={version}, obj_count={object_count}")

        self._parse_pack_objects(pack_bytes, object_count)

        self._write_refs_and_head(target_dir, head_commit_sha)

        # finding the tree this commit points to, by reading the commit object we just wrote
        commit_content = self._get_object_content(self._object_path(head_commit_sha))
        _, _, commit_body = commit_content.partition(b'\x00')
        first_line = commit_body.split(b'\n')[0]
        root_tree_sha = first_line.split(b' ')[1].decode('ascii')

        self._checkout_tree(root_tree_sha, target_dir)

        print(f"Cloned into : {target_dir}")
    # finishhhhhhhhhhhhh
        

    # -------- HELPER FUNCTIONS --------

    # 1. Reading and Decompress a zlib-compressed object file
    def _get_object_content(self, file_path):
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'rb') as f: # zlib-compressed - Binary format
                compressed_data = f.read()
            return zlib.decompress(compressed_data)

        except (zlib.error, OSError):
            return None
        

    # 2. Computing sha1 hash 
    def _compute_sha1_hash(self, input_bytes: bytes): 
        # create object of hashlib -> update with encoded file data -> hexdigest function
        sha1_hash = hashlib.sha1()
        sha1_hash.update(input_bytes)

        return sha1_hash.hexdigest()
    

    # 3. Reading, hashing, compressing, and optionally writing
    def _write_blob(self, file_path: str, write_to_disk: bool) -> str:

        # Need to : Read file -> Add header -> Calculate sha1 hash -> compress with zlib -> write to Git database
        try:
            with open(file_path, 'rb') as f:
                file_content_bytes= f.read()
        except Exception as e:
            print(f"Error in reading the file: {e}", file=sys.stderr)
            sys.exit(1)

        file_content_size = len(file_content_bytes)
        header_bytes = f"blob {file_content_size}\x00".encode('ascii')
        file_content_with_header = header_bytes + file_content_bytes

        if write_to_disk:
            return self._write_object(file_content_with_header)

        return self._compute_sha1_hash(file_content_with_header)

    # 4. finding object path -> making dir if required -> returning path
    def _object_path(self, sha, make_dir=False):
        path_dir = os.path.join(self.git_dir, Git.OBJECTS_DIR, sha[:2])
        if make_dir:
            os.makedirs(path_dir, exist_ok=True)
        return os.path.join(path_dir, sha[2:])

    # 5. computing sha1 hash, getb object path via _object_path func, zlib compress the content, writing to the disk, return the hex SHA
    def _write_object(self, content_with_header: bytes)->str:
        sha1 = self._compute_sha1_hash(content_with_header)
        path_new_object = self._object_path(sha1, make_dir=True)

        if os.path.exists(path_new_object):
            return sha1

        compressed_data = zlib.compress(content_with_header)
        try:
            with open(path_new_object, 'wb') as f:
                f.write(compressed_data)
        except Exception as e:
            print(f"Error while writing to file : {e}", file=sys.stderr)
            sys.exit(1)

        return sha1

    # 6. Sending GET request for git clone implemetation - get pkt line response
    def _discover_refs(self, repo_url):
        url = f"{repo_url}/info/refs?service=git-upload-pack"
        req = urllib.request.Request(url, headers={'User-Agent': 'git/2.0.0'})
        with urllib.request.urlopen(req) as response:
            return response.read()

    # 7. packet line parser
    def _parse_pkt_lines(self, data: bytes):
        lines = []
        i = 0
        while i < len(data):
            length_hex = data[i:i+4]
            length = int(length_hex, 16)

            if length == 0: # flush packet found
                i += 4
                continue

            line  = data[i+4 : i+length]
            lines.append(line)
            i += length

        return lines

    # 8. Parsing pkt line from get request to get head commit sha
    def _get_head_commit_sha(self, lines)->str :
        sha, _ , refs = lines[1].partition(b'\x20')
        return sha.decode('ascii')

    # 9. requesting the pack using head commit sha
    def _request_pack(self, repo_url, want_sha: bytes)->bytes:
        want_line = self._build_pkt_line(b"want " + want_sha + b"\n")
        flush = b"0000"
        done_line = self._build_pkt_line(b"done\n")

        body = want_line + flush + done_line

        url = f"{repo_url}/git-upload-pack"
        req = urllib.request.Request(
            url, 
            data=body,
            headers={
                'User-Agent': 'git/2.0.0',
                'Content-Type': 'application/x-git-upload-pack-request',
                'Accept': 'application/x-git-upload-pack-result',
            }
        )
        with urllib.request.urlopen(req) as response:
            return response.read()


    # 10. building a pkt line - reverse of parsing
    def _build_pkt_line(self, content:bytes)->bytes:
        length = len(content) + 4
        return f"{length:04x}".encode('ascii') + content

    # 11. Extract pack data, excluding the pkt line from the POST request
    def _extract_pack_bytes(self, pack_data: bytes)->bytes:
        pack_start = pack_data.find(b'PACK')
        return pack_data[pack_start:]

    # 12. PACK has a conatining version and object number
    def _parse_pack_header(self, pack_bytes: bytes):
        magic = pack_bytes[0:4]
        version = struct.unpack('>I', pack_bytes[4:8])[0] # 4 byte version field
        object_count = struct.unpack('>I', pack_bytes[8:12])[0]
        return version, object_count

    # 13. Moving to objects of PACK - parsing the object header - lovely bit manipulation 
    def _read_object_header(self, pack_data: bytes, offset: int):
        # we need to traverse byte by byte now
        byte = pack_data[offset]
        obj_type = (byte >> 4) & 0x7    # buts 6-4
        size = byte & 0xF               # bits 3-0
        shift = 4
        offset += 1

        while byte & 0x80:              # bit 7 set -> more byte parsing
            byte = pack_data[offset]
            size |= (byte & 0x7F) << shift
            shift += 7
            offset += 1

        return obj_type, size, offset

    # 14. Decompressing the data after parsing the object header
    def _decompress_object(self, pack_data:bytes, offset: int):
        decompressor = zlib.decompressobj()
        decompressed = decompressor.decompress(pack_data[offset: ])
        consumed = len(pack_data[offset:]) - len(decompressor.unused_data)
        return decompressed, offset + consumed

    # 15. this will used the above two function to parse the objects of PACK
    def _parse_pack_objects(self, pack_bytes: bytes, object_count: int):
        offset = 12 # skipping past "PACK" + version (4) + object_count(4)

        type_names = {
            self.OBJ_COMMIT: "commit",
            self.OBJ_TREE: "tree",
            self.OBJ_BLOB: "blob",
        }

        resolved = {} # offset where object started

        # we will traverse each object one by one
        for _ in range(object_count):
            obj_start = offset
            obj_type, size, offset = self._read_object_header(pack_bytes, offset)

            if obj_type == self.OBJ_REF_DELTA:
                back_distance, offset = self._read_ofs_delta_offset(pack_bytes, offset)
                base_offset = obj_start - back_distance # where the base object started
                delta_content, offset = self._decompress_object(pack_bytes, offset) # decompressing the diff instruction

                base_type, base_content = resolved[base_offset]
                content = self._apply_delta(base_content, delta_content) # reconstructing a real contetn

                resolved[obj_start] = (base_type, content) # delta inherits its base type
                type_name = type_names[base_type]
                header = f"{type_name} {len(content)}\x00".encode('ascii')
                self._write_object(header + content) # writing to the disk
                continue

            if obj_type == self.OBJ_REF_DELTA: # base identified by full 20 bytes sha and not offset
                print("Skipping REF Delta for now")
                offset += 20 # the 20 bytes SGA
                _, offset = self._decompress_object(pack_bytes, offset)
                continue

            content, offset = self._decompress_object(pack_bytes, offset)

            # note that the decompressed data does not have the header of an usual object so we need to add that now
            resolved[obj_start] = (obj_type, content)

            type_name = type_names[obj_type]
            header = f"{type_name} {len(content)}\x00".encode('ascii')
            full_object = header + content

            self._write_object(full_object)

    # 16. Reading OFS delta offset
    def _read_ofs_delta_offset(self, pack_data:bytes, offset: int):
        byte = pack_data[offset]
        result = byte & 0x7F
        offset += 1
        while byte & 0x80:
            byte = pack_data[offset]
            result += 1 # this is git spec quirk, only for this field
            result = (result << 7) | (byte & 0x7F)
            offset += 1
        return result, offset

    # 17. Applying the delta instructions, here delta is the decompressed stream of instructions - copy from base or insert new bytes; while base is the already resolved content this delta is a diff against
    def _apply_delta(self, base:bytes, delta:bytes)->bytes:
        pos = 0

        # local helper to read the 7bit per byte varint
        def read_varint():
            nonlocal pos
            result = 0
            shift = 0
            while True:
                byte = delta[pos]
                pos += 1
                result |= (byte & 0x7F) << shift
                shift += 7
                if not (byte & 0x80):
                    break
            return result

        base_size = read_varint() # for check, not used later
        result_size = read_varint() # exopected final reconstructed size

        result = bytearray() # will build the reconstructed object content here
        while pos < len(delta):
            byte = delta[pos]
            pos += 1

            if byte & 0x80:
                # copy instruc - the msb flag is set, which say copy from base, but the rest 7 bits are also flags and not data, each flag says whether a correpsonding offset/size byte is present next
                copy_offset = 0
                copy_size = 0 

                for i in range(4): # bits 0 se 3 of instruction byte - will tell aboutb upto 4 offset bytes
                    if byte & (1 << i):
                        copy_offset |= delta[pos] << (8 * i)
                        pos += 1

                for i in range(3):  # bits 4 se 6 of instruction byte - will tell aboutb upto 3 size bytes
                    if byte & (1 << (4 + i)):
                        copy_size |= delta[pos] << (8 * i)
                        pos += 1

                if copy_size == 0: # scepific special case size 0 means 65536
                    copy_size = 0x10000

                result += base[copy_offset:copy_offset + copy_size]

            else:
                # insert instruct - new literal bytes and not from the base
                # incstruct byte own value is the length (max 127 as the top bit is 0)
                insert_size = byte
                result += delta[pos : pos + insert_size]
                pos += insert_size

        return bytes(result) # reconstructed object content

    # 18. after all objects are written, we are poiting this new repo's main branch at the commit we cloned
    def _write_refs_and_head(self, target_dir: str, commit_sha: str) :
        refs_path = os.path.join(target_dir, self.git_dir, self.REFS_DIR, self.HEADS_DIR, 'main')
        with open(refs_path, 'w') as f:
            f.write(commit_sha + '\n')
        # HEAD already points to "ref: refs/heads/main" from intit() - nothign to do there

    # 19. Walks a tree object and write real files to disk - reverse of write_tree
    def _checkout_tree(self, tree_sha: str, target_dir: str):
        tree_path = self._object_path(tree_sha)
        content = self._get_object_content(tree_path)
        header, _, body = content.partition(b'\x00')

        i = 0
        while i < len(body):
            space_ind = body.find(b'\x20', i)
            mode = body[i:space_ind]
            null_ind = body.find(b'\x00', space_ind)
            file_name = body[space_ind + 1 : null_ind].decode('utf-8')
            sha1_bytes = body[null_ind + 1 : null_ind + 21]
            sha1_hex = sha1_bytes.hex()

            full_path = os.path.join(target_dir, file_name)

            if mode == b'40000': # subtree, unleash the beauty of recursion
                os.makedirs(full_path, exist_ok=True)
                self._checkout_tree(sha1_hex, full_path)

            else: # its a blob- decompress and write real content to the disk
                blob_path = self._object_path(sha1_hex)
                blob_content = self._get_object_content(blob_path)
                _, _, file_body  = blob_content.partition(b'\x00')
                with open(full_path, 'wb') as f:
                    f.write(file_body)

            i = null_ind + 21

                






# -------- MAIN ---------

def main():

    git = Git()

    # --------- ADDING A PARSER ---------
  
    parser = argparse.ArgumentParser(description="Basic Git Implementation.")

    # ----- Setting up Subcommands ------

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title="Avialable commands"
    )

    # -- 1. Subcommand - Git Init --
    init_parser = subparsers.add_parser('init', help="initiliase a new Git repo")
    init_parser.set_defaults(func=git.init)


    # -- 2. Subcommand - Git cat-file <flag> <sha1-hash> --
    cat_file_parser = subparsers.add_parser('cat-file', help="reading the content of a Git object")

    # adding mutually exclusive flags support
    group = cat_file_parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-p', action='store_true', help='Pretty print the contents of the object')
    group.add_argument('-t', action='store_true', help='print the type of object')
    group.add_argument('-s', action='store_true', help="print byte size of the object")
    
    # parsing the hash of object
    cat_file_parser.add_argument('object_hash', type=str, help="sha1-hash of the Git object to read")
    cat_file_parser.set_defaults(func=git.cat_file)


    # -- 3. Subcommand - Git hash-object <flag> <filename> --
    hash_object_parser = subparsers.add_parser('hash-object', help="Computing the sha-1 hash of git object, and optionally storing the object to Git database")

    # adding the optional flag
    hash_object_parser.add_argument('-w', action='store_true', help="Storing the object to Git database")

    # filename
    hash_object_parser.add_argument('file_path', help="file path to caculate the sha1-hash of")
    hash_object_parser.set_defaults(func=git.hash_object)


    # -- 4. Subcommand - Git ls-tree <flag> <tree-sha1-hash> --
    ls_tree_parser = subparsers.add_parser('ls-tree', help='list the content of a tree object')

    # required tree hash
    ls_tree_parser.add_argument("tree_hash", type=str, help='SHA-1 hash of the tree object to read')

    # optional flag - --name-only
    ls_tree_parser.add_argument('--name-only', dest='name_only', action='store_true', help='Only print the names of the item')

    ls_tree_parser.set_defaults(func = git.ls_tree)


    # -- 5. SubCommand - git write-tree  --
    write_tree_parser = subparsers.add_parser('write-tree', help='creates a tree object from the current state of the staging area.')
    write_tree_parser.set_defaults(func = git.write_tree)


    # -- 6. Subcommand - git commit-tree <tree-sha> -p <commit-sha> -m <message> --
    commit_tree_parser = subparsers.add_parser('commit-tree', help="creating a commit object")

    # required tree hash
    commit_tree_parser.add_argument("tree_hash", type=str, help="SHA-1 hash of the tree object (snapshot root)")
    commit_tree_parser.add_argument('-p', '--parent', type=str, action='store', help="SHA-1 hash of parent commit")
    commit_tree_parser.add_argument('-m', '--message', type=str, action='store', required=True, help="Commit message")

    commit_tree_parser.set_defaults(func= git.commit_tree)

    # -- 7. Subcommand - git clone <github repo address> <directory name> --
    clone_parser = subparsers.add_parser("clone", help="Cloning a public repository from Github")

    clone_parser.add_argument("repo_address", type=str, help="The URL or path to the repo to clone")
    clone_parser.add_argument("directory_name", type=str, help="The path to the directory to clone into")

    clone_parser.set_defaults(func=git.clone)


    # ---- PARSE and DISPATCH -----
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()