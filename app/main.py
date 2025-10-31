import sys
import os
import zlib
import hashlib
import time
import datetime
import argparse
from urllib import request
import re

class Git:
    # hard coding - reusability - ALL_CAPS - convention variable name
    OBJECTS_DIR = 'objects'
    REFS_DIR = 'refs'
    HEAD_FILE = 'HEAD'
    HEADS_DIR = 'heads'

    def __init__(self, git_dir = '.git'):
        self.git_dir = git_dir


    # -------- GIT COMMANDS --------

    # -- 1. COMMAND : git init --
    def init(self, args): 
        # creating necessary directories - objects and refs/heads
        os.makedirs(os.path.join(self.git_dir, Git.OBJECTS_DIR), exist_ok=True)
        os.makedirs(os.path.join(self.git_dir, Git.REFS_DIR, Git.HEADS_DIR), exist_ok=True)

        # writing to head file
        head_file_path = os.path.join(self.git_dir, Git.HEAD_FILE)
        
        # Only write the file if it doesn't exist
        # This prevents 'clone' from overwriting the HEAD after checkout
        if not os.path.exists(head_file_path):
            with open(head_file_path, 'w') as f:
                f.write(f"ref: {os.path.join(Git.REFS_DIR, Git.HEADS_DIR)}/main\n")

        print("Initialized git directory")


    # -- 2. COMMAND : git cat-file <flag> <hash-of-the-file> --
    def cat_file(self, args): 
        hash_str = args.object_hash
        object_path = os.path.join(self.git_dir, Git.OBJECTS_DIR, hash_str[:2], hash_str[2:]) # the object associated with the given hash
        
        # Need content of file at the path - zlib decompression
        content = self._get_object_content(object_path)

        # Content format - <object-type>\x20<size>\x00<content>
        if content is None:
            print(f"fatal: Not a valid object name {hash_str}", file=sys.stderr)
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
        path_to_tree_object = os.path.join(self.git_dir, Git.OBJECTS_DIR, hash_of_tree_object[:2], hash_of_tree_object[2:])
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
            filename_end = null_index - 1

            filename = tree_entries[filename_start: filename_end + 1]

            # third component - sha1 hash
            sha1_start = null_index + 1
            sha1 = tree_entries[sha1_start: sha1_start + 20]

            if args.name_only:
                # currently we need to print only the file name
                print(filename.decode('utf-8'))

            else:
                mode_str = mode.decode('ascii')
                if mode_str == '100644' or mode_str == '100755' or mode_str == '1200000' or mode_str == '160000':
                    type = 'blob'
                elif mode_str == '040000':
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
                tree_object = b'tree 0\x0S\x00'
                return self._compute_sha1_hash(tree_object)

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

            tree_sha = self._compute_sha1_hash(tree_object)

            path_to_tree_dir = os.path.join(self.git_dir, Git.OBJECTS_DIR, tree_sha[:2])
            os.makedirs(path_to_tree_dir, exist_ok=True)

            path_to_tree_object = os.path.join(path_to_tree_dir, tree_sha[2:])

            try:
                with open(path_to_tree_object, 'wb') as f:
                    f.write(zlib.compress(tree_object))
            except Exception as e:
                print(f"Error writing tree object: {e}", file=sys.stderr)
                sys.exit(1)

            if dir_path == '.':
                print(tree_sha)
            return tree_sha

        except FileNotFoundError:
            print(f"Error: Directory {dir_path} not found.", file=sys.stderr)
            sys.exit(1)


    # -- 6. SubCommand - git commit-tree <tree-sha> -p <parent-commit-sha> -m <commit-message> --
    def commit_tree(self, args):
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

        sha_of_commit_object = self._compute_sha1_hash(commit_object_content)
        path_to_commit_dir = os.path.join(self.git_dir, Git.OBJECTS_DIR, sha_of_commit_object[0:2])
        os.makedirs(path_to_commit_dir, exist_ok=True)
        path_of_commit_object = os.path.join(path_to_commit_dir, sha_of_commit_object[2:])

        try:
            with open(path_of_commit_object, 'wb') as f:
                f.write(zlib.compress(commit_object_content))
        except Exception as e:
            print(f"Error writing to commit object: {e}", file=sys.stderr)
            sys.exit(1)

        print(sha_of_commit_object)

    
    # -- 7. Subcommand - git clone <github-repo-https> <dir-to-clone-to>
    def clone(self, args):
        repo_url = args.repo_address
        directory_name = args.directory_name

        # --- 1. Create directory and init ---
        try:
            if not os.path.exists(directory_name):
                os.makedirs(directory_name)
            elif not os.path.isdir(directory_name):
                print(f"fatal: '{directory_name}' exists but is not a directory.", file=sys.stderr)
                sys.exit(1)
            elif os.listdir(directory_name):
                 print(f"fatal: '{directory_name}' exists and is not empty.", file=sys.stderr)
                 sys.exit(1)

            # Change into the new directory.
            # We need to update our Git object to work from this new directory.
            os.chdir(directory_name)
            self.git_dir = os.path.join(os.getcwd(), '.git')

            self.init(args) 
            print(f"Initialized empty Git repository in {self.git_dir}/")

        except Exception as e:
            print(f"Error creating directory or initializing repo: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"Cloning into '{directory_name}'...")

        # --- 2. Ref Discovery (GET request) ---
        ref_discovery_url = f"{repo_url.rstrip('/')}/info/refs?service=git-upload-pack"
        
        try:
            with request.urlopen(ref_discovery_url) as response:
                if response.status != 200:
                    raise Exception(f"HTTP Error {response.status}: {response.reason}")
                
                response_bytes = response.read()

        except Exception as e:
            print(f"fatal: could not read from remote repository: {e}", file=sys.stderr)
            sys.exit(1)

        # --- 3. Parse Ref Discovery response ---
        # The response is in "pkt-line" format.
        # We need to parse it to find the refs we want.
        refs, capabilities = self._parse_pkt_lines(response_bytes)
        
        # Find the SHA-1 for the main branch
        head_sha = ""
        if 'refs/heads/main' in refs:
            head_sha = refs['refs/heads/main']
        elif 'refs/heads/master' in refs:
            head_sha = refs['refs/heads/master']
        else:
            print("fatal: could not find 'main' or 'master' branch", file=sys.stderr)
            sys.exit(1)

        # --- 4. Build and send POST request for PACK file ---
        upload_pack_url = f"{repo_url.rstrip('/')}/git-upload-pack"
        
        # Build the body of the POST request, also in pkt-line format
        post_data = b""
        post_data += self._create_pkt_line(f"want {head_sha}\n")
        post_data += self._create_pkt_line(None, flush=True) # Flush packet
        post_data += self._create_pkt_line("done\n")

        try:
            # Create a POST request
            post_req = request.Request(upload_pack_url, data=post_data, headers={
                'Content-Type': 'application/x-git-upload-pack-request',
                'Accept': 'application/x-git-upload-pack-result',
            })

            with request.urlopen(post_req) as response:
                if response.status != 200:
                    raise Exception(f"HTTP Error {response.status}: {response.reason}")
                
                # This is the binary data of the PACK file
                pack_file_data = response.read()

        except Exception as e:
            print(f"fatal: could not fetch PACK file: {e}", file=sys.stderr)
            sys.exit(1)
        
        # --- 5. Process the PACK file (The Hard Part) ---
        # The response starts with some pkt-lines, then the PACK data.
        # We need to find the start of the PACK data (which begins with "PACK")
        
        # A simple way to skip the pkt-line headers on the PACK file response:
        # Find the first occurrence of b'PACK'
        pack_start_index = pack_file_data.find(b'PACK')
        if pack_start_index == -1:
            print("fatal: 'PACK' header not found in response", file=sys.stderr)
            sys.exit(1)
            
        # The actual packfile starts at this index
        binary_pack_data = pack_file_data[pack_start_index:]
        
        print("Successfully fetched PACK file.")

        # --- THIS IS YOUR NEXT TASK ---
        # 1. Parse 'binary_pack_data'
        #    - Read the PACK header (signature, version, num_objects)
        # 2. Loop 'num_objects' times
        #    - Read the object header (type, size)
        #    - Read the object data (zlib-compressed)
        # 3. Handle 'delta' objects (OBJ_OFS_DELTA, OBJ_REF_DELTA)
        #    - This is the most complex part, requiring you to
        #      reconstruct objects from a base object and a diff.
        # 4. Write the reconstructed, full objects to your
        #    .git/objects directory using the same logic as _write_blob
        #    (but be careful, don't re-compress!)
        #
        # After all objects are saved:
        # 5. Create/Update '.git/refs/heads/main' (or master)
        #    with the 'head_sha'
        # 6. Update '.git/HEAD' to point to your new branch ref
        # 7. Checkout the files (read the commit, then the tree,
        #    then the blobs, and write them to the working directory)
        
        # For now, we will just stop.
        print(f"Next step: Parse the {len(binary_pack_data)} byte PACK file.")
        
        

    # -------- HELPER FUNCTIONS --------

    # 1. Reading and Decompress a zlib-compressed object file
    def _get_object_content(self, file_path):
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'rb') as f: # zlib-compressed - Binary format
                compressed_data = f.read()
            return zlib.decompress(compressed_data)

        except (zlib.error, Exception):
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
        sha1_of_file = self._compute_sha1_hash(file_content_with_header)

        if not write_to_disk:
            return sha1_of_file # Return SHA even if not writing
        
        compressed_data = zlib.compress(file_content_with_header) 
        # making dir in object using the hash result
        path_new_object_dir = os.path.join(self.git_dir, Git.OBJECTS_DIR , sha1_of_file[:2])
        os.makedirs(path_new_object_dir, exist_ok=True)

        # writing to the hash defined path
        path_new_object = os.path.join(path_new_object_dir, sha1_of_file[2:])
        try:
            with open(path_new_object, 'wb') as f:
                f.write(compressed_data)
        except Exception as e:
            print(f"Error while writing to file: {e}", file=sys.stderr)
            sys.exit(1)

        return sha1_of_file

    # 4. Create a pkt-line
    def _create_pkt_line(self, data_str: str, flush: bool = False) -> bytes:
        """
        Encodes a string into the pkt-line format.
        """
        if flush:
            return b'0000'
        
        data_bytes = data_str.encode('utf-8')
        length = len(data_bytes) + 4 # +4 for the hex length prefix
        
        # Format length as 4-digit hex
        hex_length = f"{length:04x}"
        
        return hex_length.encode('utf-8') + data_bytes

    # 5. Parse a pkt-line response
    def _parse_pkt_lines(self, response_bytes: bytes):
        """
        Parses the pkt-line formatted response from info/refs.
        """
        refs = {}
        capabilities = []
        i = 0
        
        while i < len(response_bytes):
            # Read the 4-byte hex length prefix
            hex_length = response_bytes[i:i+4].decode('utf-8')
            if hex_length == '0000':
                i += 4
                break # Flush packet, end of refs
            
            length = int(hex_length, 16)
            
            # Get the line content (length - 4 bytes for the prefix)
            line_content = response_bytes[i+4 : i+length]
            line_str = line_content.decode('utf-8').strip() #.strip() to remove trailing newline
            
            i += length # Move to the next line
            
            # The first line contains capabilities
            if i == length: # First line
                sha, ref_name_with_caps = line_str.split(' ', 1)
                ref_name, caps_str = ref_name_with_caps.split('\x00')
                refs[ref_name] = sha
                capabilities = caps_str.split(' ')
            else:
                # Subsequent lines are just 'sha ref_name'
                if line_str: # avoid processing empty lines
                    sha, ref_name = line_str.split(' ', 1)
                    refs[ref_name] = sha
                    
        return refs, capabilities



# -------- MAIN ---------

def main():

    # We must initialize Git() *before* parsing, so we can
    # potentially change the git_dir inside the 'clone' command.
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