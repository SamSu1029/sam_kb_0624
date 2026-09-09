

def test(a,b):
    try:
        if a==0:
            raise ValueError("a不能为0")
        return b/a

    except Exception as e:
        print("数据有误", e)




def test1(a,b):
    try:
        if a==0:
            raise ValueError("a不能为0")
        return b/a

    except Exception as e:
        print("数据有误", e)

if __name__ == "__main__":
    main()


