import sys
import os
import zlib

class Git:
    def __init__(self, git_dir ='.git'):
        self.git_dir = git_dir

    def init(self):
        os.makedirs(os.path.join(self.git_dir, 'objects'), exist_ok=True)
        os.makedirs(os.path.join(self.git_dir, 'refs'), exist_ok=True)

        with open(".git/HEAD", 'w') as f:
            f.write("ref: refs/heads/main\n")
        print("Initialized git directory")

    def cat_file(self, args):
        if not os.path.exists(os.path.join(self.git_dir, 'objects')):
            print("Git directory not initialised yet", file=sys.stderr)
            return
        
        if args[0] == '-p':
            if not args[1]:
                print("Usage: cat-file <flag> <hash-of-object>", file=sys.stderr)
            else:
                hash = args[1]
                object_path = os.path.join(self.git_dir, 'objects', hash[:2], hash[2:])

                content = self.decompress_file(object_path)

                # now this content has the object type and the file size after decompression
                # we need to parse this as well
                if content:
                    header, _ , body = content.partition(b'\x00')
                    print(body.decode('utf-8'), end='')
        else:
            print("Usage: cat-file <flag> <hash-of-object>", file=sys.stderr)

    def decompress_file(self, file_path):
        if not os.path.exists(file_path):
            print(f"File not found at {file_path}", file=sys.stderr)
            return
        
        try:
            with open(file_path, 'rb') as f:
                compressed_data = f.read()

            decompressed_data = zlib.decompress(compressed_data)

        except zlib.error as e:
            print(f"Zlib decompression error: {e}", file=sys.stderr)
            return 

        except Exception as e:
            print(f"An error occured: {e}", file=sys.stderr)
            return
        

def main():

    git = Git()

    if len(sys.argv) == 1:
        print(f"pass argument with the function", file=sys.stderr)
    elif len(sys.argv) == 2:
        command = sys.argv[1]
    else:
        command = sys.argv[1]
        arguments = sys.argv[2:]

    if command == "init":
        git.init()
    elif command == "cat-file":
        git.cat_file(arguments)
    else:
        raise RuntimeError(f"Unknown command #{command}")


if __name__ == "__main__":
    main()
