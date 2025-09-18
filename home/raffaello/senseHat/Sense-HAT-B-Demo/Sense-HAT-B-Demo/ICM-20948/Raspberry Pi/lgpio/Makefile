ICM20948_DEMO:main.o ICM20948.o
	gcc -Wall -o ICM20948_DEMO main.o ICM20948.o -llgpio -lm -std=gnu99
main.o: main.c ICM20948.h
	gcc -Wall -c main.c -llgpio -lm -std=gnu99
ICM20948.o: ICM20948.c ICM20948.h
	gcc -Wall -c ICM20948.c -llgpio -lm -std=gnu99	
clean:
	rm main.o ICM20948.o ICM20948_DEMO