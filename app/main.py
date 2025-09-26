import sys
import os
import zlib
import hashlib

class Git:
    # hard coding some name for reusability across class - ALL_CAPS is a convention for variable name for a class
    OBJECTS_DIR = 'objects'
    REFS_DIR = 'refs'
    HEAD_FILE = 'HEAD'
    HEADS_DIR = 'heads'

    def __init__(self, git_dir ='.git'):
        self.git_dir = git_dir

    # -------- INITIALISING GIT ---------

    def init(self): 
        # creating necessary directories - objects and refs/heads
        os.makedirs(os.path.join(self.git_dir, Git.OBJECTS_DIR), exist_ok=True)
        os.makedirs(os.path.join(self.git_dir, Git.REFS_DIR, Git.HEADS_DIR), exist_ok=True)

        # writing to head file
        with open(os.path.join(self.git_dir, Git.HEAD_FILE), 'w') as f:
            f.write(f"ref: {os.path.join(Git.REFS_DIR, Git.HEADS_DIR)}/main\n")

        print("Initialized git directory")


    # -------- GIT COMMANDS --------

    # Command : git cat-file <flag> <hash-of-the-file>
    def cat_file(self, args): 
        if len(args) < 2:
            print(f"Usage: cat-file <flag> <hash>", file=sys.stderr)
            sys.exit(1)

        flag = args[0]
        hash_str = args[1]
        object_path = os.path.join(self.git_dir, Git.OBJECTS_DIR, hash_str[:2], hash_str[2:]) # the object associated with the given hash
        
        # Need content of file at the path - zlib decompression
        content = self._get_object_content(object_path)

        # Content format - <object-type> <size>\x00<content>
        if content is None:
            print(f"fatal: Not a valid object name {hash_str}", file=sys.stderr)
            sys.exit(1)

        header, _ , body = content.partition(b'\x00')
            
        if flag == '-p':
            print(body.decode('utf-8'), end='') # content in byte format - converting to string format
        else:
            print("Usage: cat-file <flag> <hash-of-object>", file=sys.stderr)

    # Command: git hash-object <flag> <file-name>
    def hash_object(self, args):
        if len(args) < 2 or args[0] != '-w':
            print(f"Usage: hash-object -w file-name", file=sys.stderr)
            sys.exit(1)

        if not os.path.exists(args[1]):
            print(f"fatal: file does not exist.")
            sys.exit(1)

        # Need to : Read file -> Add header to file -> Calculate the sha1 hash -> compress file using zlib -> write to the objects/hash[:2] path
        try:
            with open(args[1], 'rb') as f:
                file_content_bytes= f.read()
        except Exception as e:
            print(f"Error in reading the file: {e}", file=sys.stderr)
            sys.exit(1)

        file_content_size = len(file_content_bytes)
        header_bytes = f"blob {file_content_size}\x00".encode('ascii')
        file_content_with_header = header_bytes + file_content_bytes
        sha1_of_file = self._compute_sha1_hash(file_content_with_header)
        compressed_data = zlib.compress(file_content_with_header, level=9) 
        
        # priting the hash to stdout
        print(sha1_of_file)

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

# -------- MAIN FUNCTION --------

def main():

    # Exiting for the case when no command passed with the _.sh exectuion 
    if len(sys.argv) < 2:
        print(f"Usage: <command> [args]", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    arguments = sys.argv[2:]

    # Creating an object of the Git class
    git = Git()

    if command == "init":
        git.init()
    elif command == "cat-file":
        git.cat_file(arguments)
    elif command == "hash-object":
        git.hash_object(arguments)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
