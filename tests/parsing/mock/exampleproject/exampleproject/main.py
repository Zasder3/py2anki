"""See if we can resolve bubbling up imports using __all__."""


from exampleproject.subpackage2.nested.extranested import deepfn


def main():
    print(deepfn())


if __name__ == "__main__":
    main()
