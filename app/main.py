import sys
import os
import zlib

class Git:
    def __init__(self, git_dir ='.git'):
        self.git_dir = git_dir

    def init(self): # Initialising a new Git repo
        # creating necessary directories
        os.makedirs(os.path.join(self.git_dir, 'objects'), exist_ok=True)
        os.makedirs(os.path.join(self.git_dir, 'refs', 'heads'), exist_ok=True)

        # writing to head file
        with open(".git/HEAD", 'w') as f:
            f.write("ref: refs/heads/main\n")

        print("Initialized git directory")

    def cat_file(self, args): # implementing git cat-file <flag> function
        if len(args) < 2:
            print(f"Usage: cat-file <flag> <hash>", file=sys.stderr)
            sys.exit(1)

        hash_str = args[1]

        object_path = os.path.join(self.git_dir, 'objects', hash_str[:2], hash_str[2:])

        flag = args[0]
        
        if flag == '-p':
            content = self._get_object_content(object_path)

            # now this content has the object type and the file size after decompression
            # we need to parse this as well
            if content:
                header, _ , body = content.partition(b'\x00')
                print(body.decode('utf-8'), end='')

        else:
            print("Usage: cat-file <flag> <hash-of-object>", file=sys.stderr)

    def _get_object_content(self, file_path):
        # a helper method to read and decompress a zlib-compressed object file
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'rb') as f:
                compressed_data = f.read()
            return zlib.decompress(compressed_data)

        except (zlib.error, Exception):
            return None

def main():

    if len(sys.argv) < 2:
        print(f"Usage: <command> [args]", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    arguments = sys.argv[2:]

    git = Git()

    if command == "init":
        git.init()
    elif command == "cat-file":
        git.cat_file(arguments)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
