import sys
import os
import zlib
import hashlib
import argparse

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
        with open(os.path.join(self.git_dir, Git.HEAD_FILE), 'w') as f:
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

        sha1 = self._get_object_content(args.file_path, args.w)
        
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
    def write_tree(self, args, directory_path = './'):
        tree_entries_str = b''
        entries = []

        # Iterating over the Dir
        dir_path = directory_path

        try:
            contents = os.listdir(dir_path)

            if not contents:
                # empty directory
                tree_object = b'tree 0\x00'
                return self._compute_sha1_hash(tree_object)

            for object in contents:
                object_path = os.path.join(directory_path, object)
                if os.path.isfile(object_path):
                    # Need - sha1 hash(20 byte), mode, filename
                    blob_sha1_hex = self._write_blob(object_path, True)
                    # Mode
                    stat_info = os.stat(object_path)
                    blob_mode = stat_info.st_mode
                    
                    entries.append(str(blob_mode).encode('utf-8') + b'\x20' + object.encode('utf-8') + b'\x00' + blob_sha1_hex.encode('utf-8'))

                elif os.path.isdir(object_path):
                    sub_tree_sha_hex = self.write_tree(None, object_path)
                    entries.append(b'040000' + b'\x20' + object.encode('utf-8') + b'\x00' + sub_tree_sha_hex.encode('utf-8'))

            entries.sort()
            for entry in entries:
                tree_entries_str += entry
            size_of_tree_object = len(tree_entries_str)
            tree_object = b'tree ' + str(size_of_tree_object).encode('utf-8') + b'\x00' + tree_entries_str

            tree_sha = self._compute_sha1_hash(tree_object)

            path_to_tree_object = os.path.join(self.git_dir, Git.OBJECTS_DIR, tree_sha[:2], tree_sha[2:])

            try:
                with open(path_to_tree_object, 'wb') as f:
                    f.write(zlib.compress(tree_object))
            except Exception as e:
                print(f"Error writing tree object: {e}", file=sys.stderr)
                sys.exit(1)

            return tree_sha

        except FileNotFoundError:
            print(f"Error: Directory {object_path} not found.", file=sys.stderr)
            sys.exit(1)

        

    # -------- HELPER FUNCTIONS --------

    # Reading and Decompress a zlib-compressed object file
    def _get_object_content(self, file_path):
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'rb') as f: # zlib-compressed - Binary format
                compressed_data = f.read()
            return zlib.decompress(compressed_data)

        except (zlib.error, Exception):
            return None
        
    # Computing sha1 hash 
    def _compute_sha1_hash(self, input_bytes: bytes): 
        # create object of hashlib -> update with encoded file data -> hexdigest function
        sha1_hash = hashlib.sha1()
        sha1_hash.update(input_bytes)

        return sha1_hash.hexdigest()
    
    # Reading, hashing, compressing, and optionally writing
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
            return
        
        compressed_data = zlib.compress(file_content_with_header, level=9) 
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
    hash_object_parser = subparsers.add_parser('hash-object', help="Computing the sha-1 hash of git object, and optionally storing the objec to Git database")

    # adding the optional flag
    hash_object_parser.add_argument('-w', action='store_true', help="Storing the object to Git database")

    # filename
    hash_object_parser.add_argument('file_path', help="file path to caculate the sha1-hash of")
    hash_object_parser.set_defaults(func=git.hash_object)

    # -- 4. Subcommand - Git ls-tree <flag> <tree-sha1-hash> --
    ls_tree_parser = subparsers.add_parser('ls-tree', help='list the content of a tree object')

    # required tree hash
    ls_tree_parser.add_argument("tree_hash", help='SHA-1 hash of the tree object to read')

    # optional flag - --name-only
    ls_tree_parser.add_argument('--name-only', dest='name_only', action='store_true', help='Only print the names of the item')

    ls_tree_parser.set_defaults(func = git.ls_tree)

    # -- 5. SubCommand - git write-tree  --
    write_tree_parser = subparsers.add_parser('write-tree', help='creates a tree object from the current state of the staging area.')
    write_tree_parser.set_defaults(func = git.write_tree)

    # ---- PARSE and DISPATCH -----
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()